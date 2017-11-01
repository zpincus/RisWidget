# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
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

from contextlib import ExitStack
import numpy
from PyQt5 import Qt

_NEXT_QGRAPHICSITEM_USERTYPE = Qt.QGraphicsItem.UserType

def generate_unique_qgraphicsitem_type():
    """Returns a value to return from QGraphicsItem.type() overrides (which help
    Qt and PyQt return objects of the right type from any call returning QGraphicsItem
    references; for details see http://www.riverbankcomputing.com/pipermail/pyqt/2015-January/035302.html
    and https://bugreports.qt.io/browse/QTBUG-45064)

    This function will not return the same value twice and should be
    used to generate type values for all custom item classes that may
    have instances in the same scene."""
    global _NEXT_QGRAPHICSITEM_USERTYPE
    _NEXT_QGRAPHICSITEM_USERTYPE += 1
    return _NEXT_QGRAPHICSITEM_USERTYPE

_GL_CACHE = {}

def QGL():
    current_thread = Qt.QThread.currentThread()
    if current_thread is None:
        # We are probably being called by a destructor being called by an at-exit cleanup routine, but too much
        # Qt infrastructure has already been torn down for whatever is calling us to complete its cleanup.
        return
    context = Qt.QOpenGLContext.currentContext()
    if context is None:
        raise RuntimeError('There is no current OpenGL context.')
    assert current_thread is context.thread()
    # Attempt to return cache entry, a Qt.QOpenGLVersionFunctions object...
    try:
        return _GL_CACHE[context]
    except KeyError:
        pass
    # There is no entry for the current OpenGL context in our cache.  Acquire, cache, and return a
    # Qt.QOpenGLVersionFunctions object.
    try:
        GL = context.versionFunctions()
        if GL is None:
            # Some platforms seem to need version profile specification
            vp = Qt.QOpenGLVersionProfile()
            vp.setProfile(Qt.QSurfaceFormat.CompatibilityProfile)
            vp.setVersion(2, 1)
            GL = context.versionFunctions(vp)
    except ImportError:
        # PyQt5 v5.4.0 and v5.4.1 provide access to OpenGL functions up to OpenGL 2.0, but we have made
        # an OpenGL 2.1 context.  QOpenGLContext.versionFunctions(..) will, by default, attempt to return
        # a wrapper around QOpenGLFunctions2_1, which has failed in the try block above.  Therefore,
        # we fall back to explicitly requesting 2.0 functions.  We don't need any of the C _GL 2.1
        # constants or calls, anyway - these address non-square shader uniform transformation matrices and
        # specification of sRGB texture formats, neither of which we use.
        vp = Qt.QOpenGLVersionProfile()
        vp.setProfile(Qt.QSurfaceFormat.CompatibilityProfile)
        vp.setVersion(2, 0)
        GL = context.versionFunctions(vp)
    if GL is None:
        raise RuntimeError('Failed to retrieve QOpenGL.')
    if not GL.initializeOpenGLFunctions():
        raise RuntimeError('Failed to initialize OpenGL wrapper namespace.')
    _GL_CACHE[context] = GL
    context.aboutToBeDestroyed.connect(lambda: _GL_CACHE.pop(context))
    return GL


MSAA_SAMPLE_COUNT = 2
SWAP_INTERVAL = 0
GL_QSURFACE_FORMAT = None
def create_default_QSurfaceFormat():
    global GL_QSURFACE_FORMAT
    if GL_QSURFACE_FORMAT is not None:
        return
    GL_QSURFACE_FORMAT = Qt.QSurfaceFormat()
    GL_QSURFACE_FORMAT.setRenderableType(Qt.QSurfaceFormat.OpenGL)
    GL_QSURFACE_FORMAT.setVersion(2, 1)
    GL_QSURFACE_FORMAT.setProfile(Qt.QSurfaceFormat.CompatibilityProfile)
    GL_QSURFACE_FORMAT.setSwapBehavior(Qt.QSurfaceFormat.DoubleBuffer)
    GL_QSURFACE_FORMAT.setStereo(False)
    GL_QSURFACE_FORMAT.setSwapInterval(SWAP_INTERVAL)
    GL_QSURFACE_FORMAT.setSamples(MSAA_SAMPLE_COUNT)
    GL_QSURFACE_FORMAT.setRedBufferSize(8)
    GL_QSURFACE_FORMAT.setGreenBufferSize(8)
    GL_QSURFACE_FORMAT.setBlueBufferSize(8)
    GL_QSURFACE_FORMAT.setAlphaBufferSize(8)
    Qt.QSurfaceFormat.setDefaultFormat(GL_QSURFACE_FORMAT)

class _GlQuad:
    def __init__(self):
        if Qt.QOpenGLContext.currentContext() is None:
            raise RuntimeError("A QOpenGLContext must be current when a _GlQuad is instantiated.")
        self.vao = Qt.QOpenGLVertexArrayObject()
        self.vao.create()
        vao_binder = Qt.QOpenGLVertexArrayObject.Binder(self.vao)
        quad = numpy.array([1.1, -1.1,
                            -1.1, -1.1,
                            -1.1, 1.1,
                            1.1, 1.1], dtype=numpy.float32)
        self.buffer = Qt.QOpenGLBuffer(Qt.QOpenGLBuffer.VertexBuffer)
        self.buffer.create()
        self.buffer.bind()
        try:
            self.buffer.setUsagePattern(Qt.QOpenGLBuffer.StaticDraw)
            self.buffer.allocate(quad.ctypes.data, quad.nbytes)
        finally:
            # Note: the following release call is essential.  Without it, if a QPainter is active, QPainter will never work for
            # again for the widget with the active painter!
            self.buffer.release()
        Qt.QApplication.instance().aboutToQuit.connect(self._on_qapplication_about_to_quit)

    def _on_qapplication_about_to_quit(self):
        # TODO: is this necessary??
        # Unlike __init__, _on_qapplication_about_to_quit is not called directly by us, and we can not guarantee that
        # an OpenGL context is current
        with ExitStack() as estack:
            if Qt.QOpenGLContext.currentContext() is None:
                offscreen_surface = Qt.QOffscreenSurface()
                offscreen_surface.setFormat(GL_QSURFACE_FORMAT)
                offscreen_surface.create()
                gl_context = Qt.QOpenGLContext()
                if hasattr(Qt.QOpenGLContext, 'globalShareContext'):
                    gl_context.setShareContext(Qt.QOpenGLContext.globalShareContext())
                gl_context.setFormat(GL_QSURFACE_FORMAT)
                gl_context.create()
                gl_context.makeCurrent(offscreen_surface)
                estack.callback(gl_context.doneCurrent)
            self.vao.destroy()
            self.vao = None
            self.buffer.destroy()
            self.buffer = None

_GL_QUAD = None
def GL_QUAD():
    global _GL_QUAD
    if _GL_QUAD is None:
        _GL_QUAD = _GlQuad()
    return _GL_QUAD