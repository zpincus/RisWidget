# This code is licensed under the MIT License (see LICENSE file for details)

import atexit
import pkg_resources
import signal

import numpy
from PyQt5 import Qt
import sip

from . import async_texture

_QAPPLICATION = None
ICON = None

def init_qapplication(icon_resource_path=(__name__, 'icon.svg')):
    global _QAPPLICATION
    if _QAPPLICATION is None:
        # It seems to work even if there is an already-extant QApplication
        # instance (e.g. started by matplotlib or whatnot). So maybe the below
        # test isn't needed? TODO: verify that this is the case on all platforms...
        # assert Qt.QApplication.instance() is None
        pre_qapp_initialization()
        _QAPPLICATION = Qt.QApplication([])

        if icon_resource_path is not None:
            ICON = Qt.QIcon(pkg_resources.resource_filename(*icon_resource_path))
            _QAPPLICATION.setWindowIcon(ICON)

        try:
            # are we running in IPython?
            import IPython
            ipython = IPython.get_ipython() # only not None if IPython is currently running
        except ModuleNotFoundError:
            ipython = None

        if ipython is not None:
            # If iPython is running, turn on the GUI integration
            ipython.enable_gui('qt5')
            # QApplication.aboutToQuit is not emitted when exiting via IPython
            # so register a handler to do so
            atexit.register(_emit_about_to_quit)

        else:
            # install signal handlers so that Qt can be interrupted by control-c to quit
            def sigint_handler(*args):
                """Handler for the SIGINT signal."""
                Qt.QApplication.quit()
            signal.signal(signal.SIGINT, sigint_handler)
            # now arrange for the QT event loop to allow the python interpreter to
            # run occasionally. Otherwise it never runs, and hence the signal handler
            # would never get called.
            timer = Qt.QTimer()
            timer.start(100)
            # add a no-op callback for timeout. What's important is that the python interpreter
            # gets a chance to run so it can see the signal and call the handler.
            timer.timeout.connect(lambda: None)
            _QAPPLICATION._timer = timer
    return _QAPPLICATION


MSAA_SAMPLE_COUNT = 2
SWAP_INTERVAL = 0
GL_QSURFACE_FORMAT = None
def pre_qapp_initialization():
    Qt.QApplication.setAttribute(Qt.Qt.AA_ShareOpenGLContexts)
    sip.setdestroyonexit(False)

    global GL_QSURFACE_FORMAT
    assert GL_QSURFACE_FORMAT is None
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

def _emit_about_to_quit():
    # With IPython's Qt event loop integration installed, the Qt.QApplication.aboutToQuit signal is not emitted
    # when the Python interpreter exits. However, we must do certain things before last-pass garbage collection
    # at interpreter exit time in order to avoid segfaulting, and these things are done in response to the
    # Qt.QApplication.aboutToQuit signal. Fortunately, we can cause Qt.QApplication.aboutToQuit emission
    # ourselves. Doing so at exit time prompts our cleanup routines, avoiding segfault upon exit.
    app = Qt.QApplication.instance()
    if app is None:
        return
    app.aboutToQuit.emit()

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


_QGL_CACHE = {}
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
        return _QGL_CACHE[context]
    except KeyError:
        pass
    # There is no entry for the current OpenGL context in our cache.  Acquire, cache, and return a
    # Qt.QOpenGLVersionFunctions object.
    QGL = context.versionFunctions()
    if QGL is None:
        # Some platforms seem to need version profile specification
        vp = Qt.QOpenGLVersionProfile()
        vp.setProfile(Qt.QSurfaceFormat.CompatibilityProfile)
        vp.setVersion(2, 1)
        QGL = context.versionFunctions(vp)
    if QGL is None:
        raise RuntimeError('Failed to retrieve QOpenGL.')
    if not QGL.initializeOpenGLFunctions():
        raise RuntimeError('Failed to initialize OpenGL wrapper namespace.')
    _QGL_CACHE[context] = QGL
    # TODO: below seems important, but I haven't found a case where it is really necessary...
    context.aboutToBeDestroyed.connect(lambda c=context: _QGL_CACHE.pop(c))
    return QGL

class _GlQuad:
    def __init__(self):
        if Qt.QOpenGLContext.currentContext() is None:
            raise RuntimeError("A QOpenGLContext must be current when a _GlQuad is instantiated.")
        self.vao = Qt.QOpenGLVertexArrayObject()
        self.vao.create()
        quad = numpy.array([1, -1,
                            -1, -1,
                            -1, 1,
                            1, 1], dtype=numpy.float32)
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

_GL_QUAD = None
def GL_QUAD():
    global _GL_QUAD
    if _GL_QUAD is None:
        _GL_QUAD = _GlQuad()
    return _GL_QUAD