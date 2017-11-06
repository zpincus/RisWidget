# The MIT License (MIT)
#
# Copyright (c) 2016 WUSTL ZPLAB
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

import contextlib
import threading
import queue

import numpy
from OpenGL import GL
from PyQt5 import Qt

from . import shared_resources

IMAGE_TYPE_TO_GL_FORMATS = {
    'G': (Qt.QOpenGLTexture.R32F, GL.GL_RED),
    'Ga': (Qt.QOpenGLTexture.RG32F, GL.GL_RG),
    'rgb': (Qt.QOpenGLTexture.RGB32F, GL.GL_RGB),
    'rgba': (Qt.QOpenGLTexture.RGBA32F, GL.GL_RGBA)
}

NUMPY_DTYPE_TO_GL_PIXEL_TYPE = {
    numpy.bool8  : GL.GL_UNSIGNED_BYTE,
    numpy.uint8  : GL.GL_UNSIGNED_BYTE,
    numpy.uint16 : GL.GL_UNSIGNED_SHORT,
    numpy.float32: GL.GL_FLOAT}

class AsyncTexture:
    def __init__(self, image):
        self.data = image.data
        self.format, self.source_format = IMAGE_TYPE_TO_GL_FORMATS[image.type]
        self.source_type = NUMPY_DTYPE_TO_GL_PIXEL_TYPE[self.data.dtype.type]
        self.done = threading.Event()
        self.status = 'waiting'
        UPLOAD_MANAGER.upload_thread.enqueue(self)

    def bind(self, tmu):
        self.done.wait()
        if self.status == 'exception':
            raise self.exception
        self.texture.bind(tmu)

    def release(self, tmu):
        self.texture.release(tmu)

    def __del__(self):
        if self.status == 'uploaded':
            UPLOAD_MANAGER.destroy_texture(self.texture)

class TextureUploadManager:
    def __init__(self):
        self._upload_thread = None
        self._allow_destroy = True

    @property
    def upload_thread(self):
        if self._upload_thread is None:
            self._upload_thread = TextureUploadThread()
            self.gl_context = Qt.QOpenGLContext()
            self.gl_context.setShareContext(Qt.QOpenGLContext.globalShareContext())
            self.gl_context.setFormat(shared_resources.GL_QSURFACE_FORMAT)
            # TODO: is below really not necessary?
            # Qt.QApplication.instance().aboutToQuit.connect(self.shut_down)
        return self._upload_thread

    def destroy_texture(self, texture):
        if not self._allow_destroy:
            print('destroying too late :(')
            return
        with contextlib.ExitStack() as estack:
            if Qt.QOpenGLContext.currentContext() is None:
                self.gl_context.makeCurrent(self._upload_thread.offscreen_surface)
                estack.callback(self.gl_context.doneCurrent)
            texture.destroy()

    def shut_down(self):
        # TODO: any of this necessary?
        if self._upload_thread is not None:
            self._upload_thread.shut_down()
        self._allow_destroy = False
        self.gl_context.deleteLater()

UPLOAD_MANAGER = TextureUploadManager()

class TextureUploadThread(Qt.QThread):
    def __init__(self):
        super().__init__()
        # must create offscreen surface in foreground thread, per Qt docs.
        # (note that the foreground thread runs __init__...)
        self.offscreen_surface = Qt.QOffscreenSurface()
        self.offscreen_surface.setFormat(shared_resources.GL_QSURFACE_FORMAT)
        self.offscreen_surface.create()
        self.queue = queue.Queue()
        self.running = True
        self.start()

    def enqueue(self, async_texture):
        self.queue.put(async_texture)

    def shut_down(self):
        self.running = False
        # now wake up the thread if it's blocked waiting for a texture
        self.queue.put(None)
        self.wait()

    def run(self):
        gl_context = Qt.QOpenGLContext()
        gl_context.setShareContext(Qt.QOpenGLContext.globalShareContext())
        gl_context.setFormat(shared_resources.GL_QSURFACE_FORMAT)
        if not gl_context.create():
            raise RuntimeError('Failed to create OpenGL context for background texture upload thread.')
        gl_context.makeCurrent(self.offscreen_surface)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        try:
            while self.running:
                async_texture = self.queue.get()
                if not self.running:
                    #self.running may go to false while blocked waiting on the queue
                    break
                try:
                    texture = Qt.QOpenGLTexture(Qt.QOpenGLTexture.Target2D)
                    texture.setFormat(async_texture.format)
                    texture.setWrapMode(Qt.QOpenGLTexture.ClampToEdge)
                    texture.setMipLevels(6)
                    texture.setAutoMipMapGenerationEnabled(False)
                    data = async_texture.data
                    texture.setSize(data.shape[0], data.shape[1], 1)
                    texture.allocateStorage()
                    texture.setMinMagFilters(Qt.QOpenGLTexture.LinearMipMapLinear, Qt.QOpenGLTexture.Nearest)
                    texture.bind()
                    try:
                        #TODO: use QOpenGLTexture.setData here, and pixel storage
                        # functions to allow strided arrays.
                        GL.glTexSubImage2D(
                            GL.GL_TEXTURE_2D, 0, 0, 0, data.shape[0], data.shape[1],
                            async_texture.source_format,
                            async_texture.source_type,
                            memoryview(data.swapaxes(0,1).flatten()))
                        texture.generateMipMaps()
                    finally:
                        texture.release()
                    async_texture.texture = texture
                    async_texture.status = 'uploaded'
                except Exception as e:
                    async_texture.exception = e
                    async_texture.status = 'exception'
                finally:
                    async_texture.done.set()
        finally:
            gl_context.doneCurrent()