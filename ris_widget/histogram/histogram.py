import functools
import numpy
import _histogram

_mn = _histogram.ffi.new('uint8_t *')
_mx = _histogram.ffi.new('uint8_t *')
_mn16 = _histogram.ffi.new('uint16_t *')
_mx16 = _histogram.ffi.new('uint16_t *')
_mnf = _histogram.ffi.new('float *')
_mxf = _histogram.ffi.new('float *')

_int_hists = {
    (numpy.uint16, False, False): (_histogram.lib.hist_uint16, _mn16, _mx16),
    (numpy.uint8, False, False): (_histogram.lib.hist_uint8, _mn, _mx),
    (numpy.uint16, False, True): (_histogram.lib.masked_hist_uint16, _mn16, _mx16),
    (numpy.uint8, False, True): (_histogram.lib.masked_hist_uint8, _mn, _mx),
    (numpy.uint16, True, True): (_histogram.lib.masked_ranged_hist_uint16, _mn16, _mx16),
    (numpy.uint8, True, True): (_histogram.lib.masked_ranged_hist_uint8, _mn, _mx),
    (numpy.uint16, True, False): (_histogram.lib.ranged_hist_uint16, _mn16, _mx16),
    (numpy.uint8, True, False): (_histogram.lib.ranged_hist_uint8, _mn, _mx),
}


def _scanline_bounds(r, cx, cy):
    # based on 8-connected super-circle algorithm from comments in http://www.willperone.net/Code/codecircle.php
    # and:
    # A Chronological and Mathematical Overview of Digital Circle Generation Algorithms - Introducing Efficient 4 and 8-Connected Circles
    # DOI: 10.1080/00207160.2015.1056170
    # stores start and end position (on x axis) along each scanline of the circle
    bounds = numpy.empty((2*r + 1, 2), dtype=numpy.int16)
    x = 0
    y = r
    d = -r/2
    while x <= y:
        bounds[r+y] = bounds[r-y] = cx-x, cx+x+1
        bounds[r+x] = bounds[r-x] = cx-y, cx+y+1
        if d <= 0:
            x += 1
            d += x
        else:
            x += 1
            y -= 1
            d += x-y
    return bounds

@functools.lru_cache(maxsize=16)
def _circle_mask(r, shape):
    cx, cy = numpy.round(numpy.array(shape)/2).astype(int)
    sx, sy = shape
    bounds = _scanline_bounds(r, cx, cy)
    ymin = cy - r
    ymax = cy + r + 1
    to_trim_bottom = max(0, -ymin)
    to_trim_top = max(0, ymax - sy)
    ymin += to_trim_bottom
    ymax -= to_trim_top
    bounds = bounds[to_trim_bottom:len(bounds)-to_trim_top]
    bounds = bounds.clip(0, sx).astype(numpy.uint16)
    starts = bounds[:,0].copy()
    ends = bounds[:,1].copy()
    return ymin, ymax, starts, ends

def _fast_index_first(image):
    image = numpy.asarray(image)
    if image.strides[0] > image.strides[1]:
        return image.T
    else:
        return image

def histogram(image, range=None, image_bits=None, mask_radius=None):
    """
    range: [low, high] range over which histogram is calculated
    image_bits: only applies to uint16 images. If None, images are assumed to occupy full 16-bit range.
    mask: (starts, ends), where starts and ends contain the [start, end) index for
        calculating the histogram, for each scanline row in the image.
    returns: min, max, hist
        min, max: image min and max values (within the range, if specified)
        hist: histogram
    """
    assert image.dtype.type in (numpy.float32, numpy.uint8, numpy.uint16)
    masked = mask_radius is not None
    ranged = range is not None

    i = _fast_index_first(image)
    args = [_histogram.ffi.cast('char *', i.ctypes.data), i.shape[1], i.shape[0], i.strides[1], i.strides[0]]

    if masked:
        mask_radius = int(mask_radius * image.shape[0]) # use the shape of the un-transposed image (i might be transposed)
        ymin, ymax, starts, ends = _circle_mask(mask_radius, i.shape)
        i = i[:,ymin:ymax]
        sp = _histogram.ffi.cast('uint16_t *', starts.ctypes.data)
        ep = _histogram.ffi.cast('uint16_t *', ends.ctypes.data)
        args += [sp, ep]

    if image.dtype == numpy.uint8:
        hist = numpy.zeros(256, dtype=numpy.uint32)
    else:
        hist = numpy.zeros(1024, dtype=numpy.uint32)
    args.append(_histogram.ffi.cast('uint32_t *', hist.ctypes.data))

    if image.dtype == numpy.float32:
        mn, mx = _mnf, _mxf
        if masked:
            minmax_func = _histogram.lib.masked_minmax_float
            hist_func = _histogram.lib.masked_ranged_hist_float
        else:
            minmax_func = _histogram.lib.minmax_float
            hist_func = _histogram.lib.ranged_hist_float
        minmax_args = args[:-1] + [mn, mx] # ditch the hist pointer, and add the min and max pointers
        minmax_func(*minmax_args)
        if range is None:
            range = mn[0], mx[0]
        args += [len(hist), range[0], range[1]]
    else: # integral type image
        hist_func, mn, mx = _int_hists[(image.dtype.type, ranged, masked)]
        if image.dtype == numpy.uint16:
            if ranged:
                args.append(len(hist)) # nbins arg
            else:
                if image_bits is None:
                    image_bits = 16
                assert image_bits >= 10
                args.append(image_bits - 10) # bit shift arg
        if ranged:
            args.extend(range)
        args += [mn, mx]
    hist_func(*args)
    min, max = mn[0], mx[0]
    # for float images, min and max may be outside of the range. Trim if so.
    if range is not None and image.dtype == numpy.float32:
        if min < range[0]:
            min = range[0]
        if max > range[1]:
            max = range[1]
    return min, max, hist


