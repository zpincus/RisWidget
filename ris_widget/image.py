# This code is licensed under the MIT License (see LICENSE file for details)

import ctypes

import numpy
from PyQt5 import Qt

from . import async_texture

class Image(Qt.QObject):
    """An instance of the Image class is a wrapper around a Numpy ndarray representing a single image.

    Images are immutable: do not try to change the .data or .valid_range attributes after construction.

    The .data array can be modified in-place after construction, however: just call .refresh() afterward.
    """
    # TODO: update documentation after image simplification
    changed = Qt.pyqtSignal(object)

    NUMPY_DTYPE_TO_RANGE = {
        numpy.bool8  : (False, True),
        numpy.uint8  : (0, 255),
        numpy.uint16 : (0, 65535),
        numpy.float32: (-numpy.inf, numpy.inf)}

    def __init__(self, data, image_bits=None, name=None, parent=None):
        """
        image_bits: only applies to uint16 images. If None, images are assumed to occupy full 16-bit range.
        The shape of image and mask data is interpreted as (x,y) for 2-d arrays and (x,y,c) for 3-d arrays.  If your image or mask was loaded as (y,x),
        array.T will produce an (x,y)-shaped array.  In case of (y,x,c) image data, array.swapaxes(0,1) is required."""
        super().__init__(parent)

        data = numpy.asarray(data)
        if not (data.ndim == 2 or (data.ndim == 3 and data.shape[2] in (2,3,4))):
            raise ValueError('data argument must be a 2D (grayscale) or 3D (grayscale with alpha, rgb, or rgba) iterable.')

        if data.dtype not in (bool, numpy.uint8, numpy.uint16, numpy.float32):
            if numpy.issubdtype(data.dtype, numpy.floating) or numpy.issubdtype(data.dtype, numpy.integer):
                data = data.astype(numpy.float32)
            else:
                raise ValueError('Image data must be integer or floating-point.')
        if image_bits is not None and data.dtype != numpy.uint16:
            raise ValueError('The image_bits argument may only be used if data is of type uint16.')

        bpe = data.itemsize
        desired_strides = (bpe, data.shape[0]*bpe) if data.ndim == 2 else (data.shape[2]*bpe, data.shape[0]*data.shape[2]*bpe, bpe)
        if desired_strides == data.strides:
            self._data = data
        else:
            self._data = numpy.ndarray(data.shape, strides=desired_strides, dtype=data.dtype)
            self._data.flat = data.flat

        if self._data.ndim == 2:
            self.type = 'G'
        else:
            self.type = {2: 'Ga', 3: 'rgb', 4: 'rgba'}[self._data.shape[2]]

        self.image_bits = image_bits
        self.size = Qt.QSize(*self._data.shape[:2])
        if data.dtype == numpy.uint16 and image_bits is not None:
            self.valid_range = 0, 2**image_bits-1
        else:
            self.valid_range = self.NUMPY_DTYPE_TO_RANGE[data.dtype.type]

        self.name = name
        self.texture = async_texture.AsyncTexture(self)
        self.refresh()

    def __repr__(self):
        return '{}; {}x{} ({})>'.format(super().__repr__()[:-1], self.size.width(), self.size.height(), self.type)

    def refresh(self, changed_region=None):
        """
        The .refresh method should be called after modifying the contents of .data.

        The .refresh method is primarily useful to cause a user interface to update in response to data changes caused by manipulation of .data or
        another numpy view of the same memory.

        If only a portion of the image changed,
        """
        self.changed.emit(changed_region)

    def generate_contextual_info_for_pos(self, x, y):
        if not (0 <= x < self.size.width() and 0 <= y < self.size.height()):
            return None

        component_format_str = '{}' if self.data.dtype != numpy.float32 else '{:.8g}'
        pos_text = '({}, {}): '.format(x, y)
        val_text = ','.join(component_format_str for c in self.type)
        if self._data.ndim == 2:
            val_text = val_text.format(self.data[x, y])
        else:
            val_text = val_text.format(*self.data[x, y])
        return pos_text + val_text

    # make data read-only to make clear that images are immutable (though the data's contents need not be)
    @property
    def data(self):
        return self._data

def array_from_qimage(qimage):
    if qimage.isNull() or qimage.format() != Qt.QImage.Format_Invalid:
        return

    if qimage.hasAlphaChannel():
        desired_format = Qt.QImage.Format_RGBA8888
        channel_count = 4
    else:
        desired_format = Qt.QImage.Format_RGB888
        channel_count = 3
    if qimage.format() != desired_format:
        qimage = qimage.convertToFormat(desired_format)
    if channel_count == 3:
        # 24-bit RGB QImage rows are padded to 32-bit chunks, which we must match
        row_stride = qimage.width() * 3
        row_stride += 4 - (row_stride % 4)
        padded = numpy.ctypeslib.as_array(ctypes.cast(int(qimage.bits()), ctypes.POINTER(ctypes.c_uint8)), shape=(qimage.height(), row_stride))
        padded = padded[:, qimage.width() * 3].reshape((qimage.height(), qimage.width(), 3))
        npyimage = numpy.empty((qimage.height(), qimage.width(), 3), dtype=numpy.uint8)
        npyimage.flat = padded.flat
    else:
        npyimage = numpy.ctypeslib.as_array(
            ctypes.cast(int(qimage.bits()), ctypes.POINTER(ctypes.c_uint8)),
            shape=(qimage.height(), qimage.width(), channel_count))
    if qimage.isGrayscale():
        # Note: Qt does not support grayscale with alpha channels, so we don't need to worry about that case
        npyimage=npyimage[...,0]
    return npyimage
