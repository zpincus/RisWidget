# This code is licensed under the MIT License (see LICENSE file for details)

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
    # dtype, ranged, masked: (hist_func, min_var, max_var)
    (numpy.uint16, False, False): (_histogram.lib.hist_uint16, _mn16, _mx16),
    (numpy.uint8, False, False): (_histogram.lib.hist_uint8, _mn, _mx),
    (numpy.uint16, False, True): (_histogram.lib.masked_hist_uint16, _mn16, _mx16),
    (numpy.uint8, False, True): (_histogram.lib.masked_hist_uint8, _mn, _mx),
    (numpy.uint16, True, True): (_histogram.lib.masked_ranged_hist_uint16, _mn16, _mx16),
    (numpy.uint8, True, True): (_histogram.lib.masked_ranged_hist_uint8, _mn, _mx),
    (numpy.uint16, True, False): (_histogram.lib.ranged_hist_uint16, _mn16, _mx16),
    (numpy.uint8, True, False): (_histogram.lib.ranged_hist_uint8, _mn, _mx),
}

def _scanline_bounds(cx, cy, r):
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
def _circle_mask(cx, cy, r, image_shape):
    sx, sy = image_shape
    bounds = _scanline_bounds(cx, cy, r)
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
    if ymin == 0 and ymax == sy and numpy.all(starts == 0) and numpy.all(ends == sx):
        # mask is just whole image...
        return None, None, None, None
    return ymin, ymax, starts, ends

def _fast_index_first(image):
    image = numpy.asarray(image)
    if image.strides[0] > image.strides[1]:
        return image.T, True
    else:
        return image, False

def histogram(image, range=(None, None), image_bits=None, mask_geometry=None):
    """
    image: 2-dimensional greyscale image, or GA, RGB, or RGBA image in (x, y, c) index order.
        If RGB(A), the RGB channels will be converted to greyscale first. Alpha channels are ignored.
    range: [low, high] range over which histogram is calculated
    image_bits: only applies to uint16 images. If None, images are assumed to occupy full 16-bit range.
    mask_geometry: (cx, cy, radius) of a vignette mask, as fractions of image.shape.
        (cx and radius will be in terms of image.shape[0], cy in terms of image.shape[1])
    returns: min, max, hist
        min, max: image min and max values (possibly outside the range, if specified)
        hist: histogram
    """
    image = numpy.asarray(image)
    assert image.dtype.type in {numpy.bool8, numpy.uint8, numpy.uint16, numpy.float32}
    if image.ndim == 3:
        if image.shape[2] in (3, 4): # RGB/RGBA
            r, g, b = numpy.rollaxis(image, -1)[:3]
            luma = 0.2126*r + 0.7152*g + 0.0722*b # use CIE 1931 linear luminance
            image = luma.astype(image.dtype)
        elif image.shape[2] == 2: # GA
            image = image[:,:,0]
    if image.ndim != 2:
        raise ValueError('Only 2D, GA, RGB, and RGBA images are supported')

    if image.dtype == numpy.bool8:
        was_bool = True
        image = image.view(numpy.uint8)
    else:
        was_bool = False
    masked = mask_geometry is not None
    range = tuple(range)
    ranged = range != (None, None)
    r_min, r_max = range

    i, transpose = _fast_index_first(image)
    if masked:
        # multiply cx, cy, and r by the shape of the original image
        cx, cy, r = (numpy.array(mask_geometry) * [image.shape[0], image.shape[1], image.shape[0]]).astype(int)
        if transpose:
            cx, cy = cy, cx
        ymin, ymax, starts, ends = _circle_mask(cx, cy, r, i.shape)
        if ymin is None:
            # mask is whole region
            masked = False
        else:
            i = i[:,ymin:ymax]
    args = [_histogram.ffi.cast('char *', i.ctypes.data), i.shape[1], i.shape[0], i.strides[1], i.strides[0]]
    if masked:
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
        if r_min is None:
            r_min = mn[0]
        if r_max is None:
            r_max = mx[0]
        args += [len(hist), r_min, r_max]
    else: # integral type image
        hist_func, mn, mx = _int_hists[(image.dtype.type, ranged, masked)]
        if image.dtype == numpy.uint16:
            if image_bits is None:
                image_bits = 16
            if ranged:
                args.append(len(hist)) # nbins arg
            else:
                assert image_bits >= 10
                args.append(image_bits - 10) # bit shift arg
        if ranged:
            if r_min is None:
                r_min = 0
            if r_max is None:
                if image.dtype == numpy.uint8:
                    r_max = 255
                else:
                    r_max = 2**image_bits - 1
            args += [int(r_min), int(r_max)]
        args += [mn, mx]
    hist_func(*args)
    if was_bool:
        hist = hist[:2]
        r_min, r_max = bool(r_min), bool(r_max)
    return mn[0], mx[0], hist

