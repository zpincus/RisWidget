# This code is licensed under the MIT License (see LICENSE file for details)

import contextlib
import threading
import queue
# import weakref
import ctypes

import numpy
from OpenGL import GL
from PyQt5 import Qt

from . import shared_resources

IMAGE_TYPE_TO_GL_FORMATS = {
    'G': (GL.GL_R32F, GL.GL_RED),
    'Ga': (GL.GL_RG32F, GL.GL_RG),
    'rgb': (GL.GL_RGB32F, GL.GL_RGB),
    'rgba': (GL.GL_RGBA32F, GL.GL_RGBA)
}

NUMPY_DTYPE_TO_GL_PIXEL_TYPE = {
    numpy.bool8  : GL.GL_UNSIGNED_BYTE,
    numpy.uint8  : GL.GL_UNSIGNED_BYTE,
    numpy.uint16 : GL.GL_UNSIGNED_SHORT,
    numpy.float32: GL.GL_FLOAT}

USE_BG_UPLOAD_THREAD = True # debug flag for testing with flaky drivers
_DEBUG_NO_TEX = False

class AsyncTexture:
    # _LIVE_TEXTURES = None
    # @classmethod
    # def _on_about_to_quit(cls):
    #     with shared_resources.offscreen_context():
    #         for t in cls._LIVE_TEXTURES:
    #             t.destroy()

    def __init__(self, image):
        # if self._LIVE_TEXTURES is None:
        #     # if we used 'self' instead of __class__, would just set _LIVE_TEXTURES for this instance
        #     __class__._LIVE_TEXTURES = weakref.WeakSet()
        #     Qt.QApplication.instance().aboutToQuit.connect(self._on_about_to_quit)
        self.data = image.data
        self.format, self.source_format = IMAGE_TYPE_TO_GL_FORMATS[image.type]
        self.source_type = NUMPY_DTYPE_TO_GL_PIXEL_TYPE[self.data.dtype.type]
        self.ready = threading.Event()
        self.status = 'waiting'
        self.texture = None

    def upload(self, upload_region=None):
        if self.texture is None and upload_region is not None:
            raise ValueError('The first time the texture is uploaded, the full region must be used.')
        if self.ready.is_set():
            # if the texture was already uploaded and done is set, make sure to
            # reset it so that bind waits for this new upload.
            self.ready.clear()
        self.status = 'uploading'
        if USE_BG_UPLOAD_THREAD:
            OffscreenContextThread.get().enqueue(self._upload, [upload_region])
        else:
            self._upload_fg(upload_region)

    def bind(self, tex_unit):
        if not self.status in ('uploading', 'uploaded'):
            raise RuntimeError('Cannot bind texture that has not been first uploaded')
        self.ready.wait()
        if hasattr(self, 'exception'):
            raise self.exception
        assert self.texture is not None
        GL.glActiveTexture(GL.GL_TEXTURE0 + tex_unit)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)

    def destroy(self):
        if self.texture is not None:
            # requires a valid context
            assert Qt.QOpenGLContext.currentContext() is not None
            GL.glDeleteTextures([self.texture])
            self.texture = None
            self.status = 'waiting'

    def _upload_fg(self, upload_region):
        assert Qt.QOpenGLContext.currentContext() is not None
        orig_unpack_alignment = GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        try:
            self._upload(upload_region)
        finally:
            # QPainter font rendering for OpenGL surfaces can break if we do not restore GL_UNPACK_ALIGNMENT
            # and this function was called within QPainter's native painting operations
            GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, orig_unpack_alignment)

    def _upload(self, upload_region):
        try:
            if self.texture is None:
                self.texture = GL.glGenTextures(1)
                alloc_texture = True
            else:
                alloc_texture = False
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
            w, h = self.data.shape[:2]

            if alloc_texture:
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAX_LEVEL, 6)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, self.format, w, h, 0,
                    self.source_format, self.source_type, self.data.ctypes.data_as(ctypes.c_void_p))
            else: # texture already exists
                if upload_region is None:
                    x = y = 0
                    data = self.data
                else:
                    x, y, w, h = upload_region
                    data = self.data[x:x+w, y:y+h]
                try:
                    GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, self.data.shape[0])
                    if not _DEBUG_NO_TEX:
                        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, x, y, w, h,
                            self.source_format, self.source_type,
                            data.ctypes.data_as(ctypes.c_void_p))
                finally:
                    GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, 0)
            # whether or not allocating texture, need to regenerate mipmaps
            if not _DEBUG_NO_TEX:
                GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
            # need glFinish to make sure that the GL calls (which run asynchronously)
            # have completed before we set self.ready
            GL.glFinish()
            self.status = 'uploaded'
        except Exception as e:
            self.exception = e
        finally:
            self.ready.set()

class OffscreenContextThread(Qt.QThread):
    _ACTIVE_THREAD = None

    @classmethod
    def get(cls):
        if cls._ACTIVE_THREAD is None:
            cls._ACTIVE_THREAD = cls()
            # TODO: is below necessary ever?
            # Qt.QApplication.instance().aboutToQuit.connect(cls._ACTIVE_THREAD.shut_down)
        return cls._ACTIVE_THREAD

    def __init__(self):
        super().__init__()
        self.queue = queue.Queue()
        self.running = True
        self.start()

    def enqueue(self, func, args):
        self.queue.put((func, args))

    # def shut_down(self):
    #     self.running = False
    #     # now wake up the thread if it's blocked waiting for a texture
    #     self.queue.put(None)
    #     self.wait()

    def run(self):
        gl_context = Qt.QOpenGLContext()
        gl_context.setShareContext(Qt.QOpenGLContext.globalShareContext())
        gl_context.setFormat(shared_resources.GL_QSURFACE_FORMAT)
        if not gl_context.create():
            raise RuntimeError('Failed to create OpenGL context for background texture upload thread.')
        gl_context.makeCurrent(shared_resources.OFFSCREEN_SURFACE)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        try:
            while self.running:
                func, args = self.queue.get()
                if not self.running:
                    #self.running may go to false while blocked waiting on the queue
                    break
                func(*args)
        finally:
            gl_context.doneCurrent()