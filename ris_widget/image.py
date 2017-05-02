# The MIT License (MIT)
#
# Copyright (c) 2014-2016 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Erik Hvatum <ice.rikh@gmail.com>

import ctypes
import numpy
import OpenGL
import OpenGL.GL as PyGL
from PyQt5 import Qt
import textwrap
from .async_texture import AsyncTexture
from .ndimage_statistics import ndimage_statistics

class Image(Qt.QObject):
    """An instance of the Image class is a wrapper around a Numpy ndarray representing a single image.

    Images are immutable: do not try to change the .data or .valid_range attributes after construction.

    The .data array can be modified in-place after construction, however: just call .refresh() afterward.
    """
    # TODO: update documentation after image simplification
    changed = Qt.pyqtSignal(object)

    IMAGE_TYPE_TO_QOGLTEX_TEX_FORMAT = {
        'G': Qt.QOpenGLTexture.R32F,
        'Ga': Qt.QOpenGLTexture.RG32F,
        'rgb': Qt.QOpenGLTexture.RGB32F,
        'rgba': Qt.QOpenGLTexture.RGBA32F}

    NUMPY_DTYPE_TO_GL_PIXEL_TYPE = {
        numpy.bool8  : PyGL.GL_UNSIGNED_BYTE,
        numpy.uint8  : PyGL.GL_UNSIGNED_BYTE,
        numpy.uint16 : PyGL.GL_UNSIGNED_SHORT,
        numpy.float32: PyGL.GL_FLOAT}

    NUMPY_DTYPE_TO_RANGE = {
        numpy.bool8  : (False, True),
        numpy.uint8  : (0, 255),
        numpy.uint16 : (0, 65535),
        numpy.float32: (-numpy.inf, numpy.inf)}

    IMAGE_TYPE_TO_GL_PIX_FORMAT = {
        'G'   : PyGL.GL_RED,
        'Ga'  : PyGL.GL_RG,
        'rgb' : PyGL.GL_RGB,
        'rgba': PyGL.GL_RGBA}

    def __init__(self, data, image_bits=None, immediate_texture_upload=True, parent=None):
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
        self.has_alpha_channel = self.type in ('Ga', 'rgba')
        if data.dtype == numpy.uint16 and image_bits is not None:
            self.valid_range = 0, 2**image_bits-1
        else:
            self.valid_range = NUMPY_DTYPE_TO_RANGE[self.dtype.type]

        self.refresh(immediate_texture_upload)

    def __repr__(self):
        num_channels = self.num_channels
        return '{}; {}x{} ({})>'.format(super().__repr__()[:-1], self.size.width(), self.size.height(), self.type)

    def refresh(self, immediate_texture_upload=True):
        """
        The .refresh method should be called after modifying the contents of .data.

        The .refresh method is primarily useful to cause a user interface to update in response to data changes caused by manipulation of .data.data or
        another numpy view of the same memory."""
        self.async_texture = AsyncTexture(
            self._data,
            self.IMAGE_TYPE_TO_QOGLTEX_TEX_FORMAT[self.type],
            self.IMAGE_TYPE_TO_GL_PIX_FORMAT[self.type],
            self.NUMPY_DTYPE_TO_GL_PIXEL_TYPE[self.dtype.type],
            immediate_texture_upload)
        self.changed.emit(self)

    def generate_contextual_info_for_pos(self, x, y):
        sz = self.size
        component_format_str = '{}' if self.data.dtype != numpy.float32 else '{:.8g}'
        if 0 <= x < sz.width() and 0 <= y < sz.height():
            # if self.name:
            #     mst = '"' + self.name + '" '
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

    @classmethod
    def from_qimage(cls, qimage, parent=None, is_twelve_bit=False):
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
        return cls(data=npyimage.copy(), parent=parent, is_twelve_bit=is_twelve_bit)
