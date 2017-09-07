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

import sip
sip.setdestroyonexit(True)

import atexit
from PyQt5 import Qt
import sys

from . import shared_resources
from . import async_texture
from . import layer
from . import layer_stack
from .qwidgets import flipbook
from .qwidgets import fps_display
from .qwidgets import layer_table
from .qwidgets import layer_stack_painter
from . import qgraphicsscenes
from .qgraphicsviews import image_view
from .qgraphicsviews import histogram_view

try:
    import freeimage
except ModuleNotFoundError:
    freeimage = None

# the pyQt input hook starts and quits a QApplication over and over. This plays
# badly with the RisWidget assumption that the aboutToQuit signal only happens
# when RisWidget needs to be torn down. So we remove the input hook, and
# rely on the (better) ipython method.
Qt.pyqtRemoveInputHook()

if sys.platform == 'darwin':
    class NonTransientScrollbarsStyle(Qt.QProxyStyle):
        def styleHint(self, sh, option=None, widget=None, returnData=None):
            if sh == Qt.QStyle.SH_ScrollBar_Transient:
                return 0
            return self.baseStyle().styleHint(sh, option, widget, returnData)

def _atexit_cleanup():
    # With IPython's Qt event loop integration installed, the Qt.QApplication.aboutToQuit signal is not emitted
    # when the Python interpreter exits.  However, we must do certain things before last-pass garbage collection
    # at interpreter exit time in order to avoid segfaulting, and these things are done in response to the
    # Qt.QApplication.aboutToQuit signal.  Fortunately, we can cause Qt.QApplication.aboutToQuit emission
    # ourselves.  Doing so at exit time prompts our cleanup routines, avoiding the segfault upon exit from
    # an IPython session owning one or more RisWidgets.
    app = Qt.QApplication.instance()
    if app is None:
        return
    # for context in shared_resources._GL_CACHE.keys():
    #     context.destroyed[Qt.QObject].disconnect(shared_resources._on_destruction_of_context_with_cached_gl)
    app.aboutToQuit.emit()

_QAPPLICATION = None
def _init_qapplication():
    shared_resources.create_default_QSurfaceFormat()
    global _QAPPLICATION
    if _QAPPLICATION is None:
        instance = Qt.QApplication.instance()
        if instance is None:
            _QAPPLICATION = Qt.QApplication(sys.argv)
        else:
            _QAPPLICATION = instance
        # are we running in IPython? If so, turn on the GUI integration
        try:
            import IPython
            ip = IPython.get_ipython() # only not None if IPython is currently running
            if ip is not None:
                ip.enable_gui('qt5')
        except ModuleNotFoundError:
            pass

class RisWidgetQtObject(Qt.QMainWindow):
    image_view_change_signal = Qt.pyqtSignal(Qt.QTransform, Qt.QRectF)

    def __init__(self, app_prefs_name=None, window_title='RisWidget', parent=None):

        _init_qapplication()

        super().__init__(parent)
        self.app_prefs_name = app_prefs_name
        self._shown = False
        # TODO: is below workaround still necessary?
        self.resize(self.size()) # QMainWindow on Qt 5.8 doesn't remember user-set size between show/hide unless a resize is explicitly called.
        # TODO: look deeper into opengl buffer swapping order and such to see if we can become compatible with OS X auto-hiding scrollbars
        # rather than needing to disable them
        if sys.platform == 'darwin':
            style = Qt.QApplication.style()
            Qt.QApplication.setStyle(NonTransientScrollbarsStyle(style))
        if window_title is not None:
            self.setWindowTitle(window_title)
        self.setAcceptDrops(True)
        shared_resources.query_gl_exts()
        async_texture._TextureCache.init()
        self.layer_stack = layer_stack.LayerStack()
        self._init_scenes_and_views()
        self._init_flipbook()
        self._init_layer_stack_painter()
        self._init_actions()
        self._init_toolbars()
        self._init_menus()
        # RisWidgetQtObject's C++ personality is the QObject-N-parent of lots of Qt stuff that does not appreciate
        # being destroyed by Python's last-pass garbage collection or even simply when no QApplication is running.
        # Therefore, we connect the running QApplication's about to quit signal to our own C++ personality's
        # deleteLater method (the final thing QApplication does as it quits, after emitting the about to quit signal,
        # is delete everything queued up for deletion by deleteLater calls).  Thus, all of our QObject offspring
        # are culled long before the Great Garbage Battle prophesied to occur at The End of The Graceful Shutdown.
        Qt.QApplication.instance().aboutToQuit.connect(self._on_about_to_quit)
        atexit.register(_atexit_cleanup)

    def _on_about_to_quit(self):
        self.deleteLater()
        atexit.unregister(_atexit_cleanup)

    def _init_scenes_and_views(self):
        self.image_scene = qgraphicsscenes.ImageScene(self, self.layer_stack)
        self.image_view = image_view.ImageView(self.image_scene, self)
        self.setCentralWidget(self.image_view)
        self.histogram_scene = qgraphicsscenes.HistogramScene(self, self.layer_stack)
        self.histogram_dock_widget = Qt.QDockWidget('Histogram', self)
        self.histogram_view, self._histogram_frame = histogram_view.HistogramView.make_histogram_view_and_frame(self.histogram_scene, self.histogram_dock_widget)
        self.histogram_dock_widget.setWidget(self._histogram_frame)
        self.histogram_dock_widget.setAllowedAreas(Qt.Qt.BottomDockWidgetArea | Qt.Qt.TopDockWidgetArea)
        self.histogram_dock_widget.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable |
            Qt.QDockWidget.DockWidgetMovable | Qt.QDockWidget.DockWidgetVerticalTitleBar)
        self.addDockWidget(Qt.Qt.BottomDockWidgetArea, self.histogram_dock_widget)
        self.layer_table_dock_widget = Qt.QDockWidget('Layer Stack', self)
        self.layer_table_model = layer_table.LayerTableModel(self.layer_stack)
        # NB: Qt.QAbstractItemView, an ancestor of InvertingProxyModel, attempts to start a QTimer as it is destroyed.  Therefore,
        # it must be destroyed before the event dispatcher thread local object is destroyed - IE, not by Python's last-pass garbage
        # collector, which collects in no particular order, often collecting the dispatcher before any stray item models.  To prompt
        # pre-last-pass destruction, it is sufficient to make all Qt.QAbstractItemView progeny QObject-parented to a QObject that
        # is definitely destroyed before the last pass.  We are careful to ensure that RisWidget instances meet this criterion.
        self.layer_table_model_inverter = layer_table.InvertingProxyModel(self)
        self.layer_table_model_inverter.setSourceModel(self.layer_table_model)
        self.layer_table_view = layer_table.LayerTableView(self.layer_table_model)
        self.layer_table_view.setModel(self.layer_table_model_inverter)
        self.layer_table_model.setParent(self.layer_table_view)
        self.layer_table_model.rowsInserted.connect(self._update_layer_stack_visibility)
        self.layer_table_model.rowsRemoved.connect(self._update_layer_stack_visibility)
        self.layer_table_model.modelReset.connect(self._update_layer_stack_visibility)
        self.layer_stack.selection_model = self.layer_table_view.selectionModel()
        self.layer_table_dock_widget.setWidget(self.layer_table_view)
        self.layer_table_dock_widget.setAllowedAreas(Qt.Qt.AllDockWidgetAreas)
        self.layer_table_dock_widget.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.Qt.TopDockWidgetArea, self.layer_table_dock_widget)
        self.layer_table_dock_widget.hide()
        self.fps_display_dock_widget = Qt.QDockWidget('FPS', self)
        self.fps_display = fps_display.FPSDisplay()
        self.image_scene.layer_stack_item.painted.connect(self.fps_display.notify)
        self.fps_display_dock_widget.setWidget(self.fps_display)
        self.fps_display_dock_widget.setAllowedAreas(Qt.Qt.AllDockWidgetAreas)
        self.fps_display_dock_widget.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.Qt.RightDockWidgetArea, self.fps_display_dock_widget)
        self.fps_display_dock_widget.hide()

    def _init_actions(self):
        self.flipbook_focus_prev_page_action = Qt.QAction(self)
        self.flipbook_focus_prev_page_action.setText('Previous Page')
        self.flipbook_focus_prev_page_action.setShortcut(Qt.Qt.Key_PageUp)
        self.flipbook_focus_prev_page_action.triggered.connect(self.flipbook.focus_prev_page)
        # self.flipbook_focus_prev_page_action.setShortcutContext(Qt.Qt.ApplicationShortcut)
        self.flipbook_focus_next_page_action = Qt.QAction(self)
        self.flipbook_focus_next_page_action.setText('Next Page')
        self.flipbook_focus_next_page_action.setShortcut(Qt.Qt.Key_PageDown)
        self.flipbook_focus_next_page_action.triggered.connect(self.flipbook.focus_next_page)
        # self.flipbook_focus_next_page_action.setShortcutContext(Qt.Qt.ApplicationShortcut)
        self.layer_stack_reset_curr_min_max_action = Qt.QAction(self)
        self.layer_stack_reset_curr_min_max_action.setText('Reset Min/Max')
        self.layer_stack_reset_curr_min_max_action.triggered.connect(self._on_reset_min_max)
        self.layer_stack_toggle_curr_auto_min_max_action = Qt.QAction(self)
        self.layer_stack_toggle_curr_auto_min_max_action.setText('Toggle Auto Min/Max')
        self.layer_stack_toggle_curr_auto_min_max_action.triggered.connect(self._on_toggle_auto_min_max)
        self.addAction(self.layer_stack_toggle_curr_auto_min_max_action) # Necessary for shortcut to work as this action does not appear in a menu or toolbar
        self.layer_stack_reset_curr_gamma_action = Qt.QAction(self)
        self.layer_stack_reset_curr_gamma_action.setText('Reset \u03b3')
        self.layer_stack_reset_curr_gamma_action.triggered.connect(self._on_reset_gamma)
        self.layer_property_stack_save_action = Qt.QAction(self)
        self.layer_property_stack_save_action.setText('Save layer property stack as...')
        self.layer_property_stack_save_action.triggered.connect(self._on_save_layer_property_stack)
        self.layer_property_stack_load_action = Qt.QAction(self)
        self.layer_property_stack_load_action.setText('Load layer property stack from file...')
        self.layer_property_stack_load_action.triggered.connect(self._on_load_layer_property_stack)
        self.layer_stack.solo_layer_mode_action.setShortcut(Qt.Qt.Key_Space)
        self.layer_stack.solo_layer_mode_action.setShortcutContext(Qt.Qt.ApplicationShortcut)
        if freeimage is not None:
            self.snapshot_action = Qt.QAction(self)
            self.snapshot_action.setText('Snapshot')
            self.snapshot_action.setToolTip('Save snapshot of displayed image(s).')
            self.snapshot_action.triggered.connect(self._on_snapshot_action)

    def _init_flipbook(self):
        self.flipbook = fb = flipbook.Flipbook(self.layer_stack, self)
        self.flipbook_dock_widget = Qt.QDockWidget('Flipbook', self)
        self.flipbook_dock_widget.setWidget(fb)
        self.flipbook_dock_widget.setAllowedAreas(Qt.Qt.RightDockWidgetArea | Qt.Qt.LeftDockWidgetArea)
        self.flipbook_dock_widget.setFeatures(Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.Qt.RightDockWidgetArea, self.flipbook_dock_widget)
        fb.pages_model.rowsInserted.connect(self._update_flipbook_visibility)
        fb.pages_model.rowsRemoved.connect(self._update_flipbook_visibility)
        fb.pages_model.modelReset.connect(self._update_flipbook_visibility)
        self.flipbook_dock_widget.hide()
        # Make the flipbook deal with drop events
        self.dragEnterEvent = self.flipbook.pages_view.dragEnterEvent
        self.dragMoveEvent = self.flipbook.pages_view.dragMoveEvent
        self.dropEvent = self.flipbook.pages_view.dropEvent

    def _init_layer_stack_painter(self):
        self.layer_stack_painter_dock_widget = Qt.QDockWidget('Painter', self)
        self.layer_stack_painter_dock_widget.setAllowedAreas(Qt.Qt.RightDockWidgetArea | Qt.Qt.LeftDockWidgetArea)
        self.layer_stack_painter_dock_widget.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.Qt.RightDockWidgetArea, self.layer_stack_painter_dock_widget)
        self.layer_stack_painter_dock_widget.hide()
        self.layer_stack_painter = None
        self.layer_stack_painter_dock_widget.toggleViewAction().toggled.connect(self._on_layer_stack_painter_dock_widget_visibility_toggled)

    def _init_toolbars(self):
        self.main_view_toolbar = self.addToolBar('Image')
        self.zoom_editor = Qt.QLineEdit()
        self.zoom_editor.setFixedWidth(68)
        self.zoom_editor.editingFinished.connect(self._on_zoom_editing_finished)
        self.zoom_editor.setAlignment(Qt.Qt.AlignCenter)
        self.main_view_toolbar.addWidget(self.zoom_editor)
        self.image_view.zoom_changed.connect(self._image_view_zoom_changed)
        self.main_view_toolbar.addAction(self.image_view.zoom_to_fit_action)
        self.main_view_toolbar.addAction(self.layer_stack_reset_curr_min_max_action)
        self.main_view_toolbar.addAction(self.layer_stack_reset_curr_gamma_action)
        self.main_view_toolbar.addAction(self.layer_stack.auto_min_max_all_action)
        self.main_view_toolbar.addAction(self.layer_stack.solo_layer_mode_action)
        self.main_view_toolbar.addAction(self.snapshot_action)
        self.dock_widget_visibility_toolbar = self.addToolBar('Dock Widget Visibility')
        self.dock_widget_visibility_toolbar.addAction(self.layer_table_dock_widget.toggleViewAction())
        self.dock_widget_visibility_toolbar.addAction(self.layer_stack_painter_dock_widget.toggleViewAction())
        self.dock_widget_visibility_toolbar.addAction(self.histogram_dock_widget.toggleViewAction())
        self.dock_widget_visibility_toolbar.addAction(self.flipbook_dock_widget.toggleViewAction())

    def _init_menus(self):
        mb = self.menuBar()
        m = mb.addMenu('File')
        m.addAction(self.layer_property_stack_save_action)
        m.addAction(self.layer_property_stack_load_action)
        m = mb.addMenu('View')
        m.addAction(self.flipbook_focus_prev_page_action)
        m.addAction(self.flipbook_focus_next_page_action)
        m.addAction(self.flipbook.toggle_playing_action)
        m.addSeparator()
        m.addAction(self.layer_stack_reset_curr_min_max_action)
        m.addAction(self.layer_stack_reset_curr_gamma_action)
        m.addAction(self.layer_stack.auto_min_max_all_action)
        m.addAction(self.layer_stack.solo_layer_mode_action)
        m.addSeparator()
        m.addAction(self.fps_display_dock_widget.toggleViewAction())

    def _on_layer_stack_painter_dock_widget_visibility_toggled(self, is_visible):
        if is_visible:
            if self.layer_stack_painter is None:
                self.layer_stack_painter = layer_stack_painter.LayerStackPainter(self.image_scene.layer_stack_item)
                self.layer_stack_painter_dock_widget.setWidget(self.layer_stack_painter)
        else:
            if self.layer_stack_painter is not None:
                self.image_scene.removeItem(self.layer_stack_painter.painter_item)
                self.layer_stack_painter = None

    def showEvent(self, event):
        if self.app_prefs_name and not self._shown:
            self._shown = True
            settings = Qt.QSettings("zplab", self.app_prefs_name)
            geometry = settings.value('main_window_geometry')
            if geometry is not None:
                self.restoreGeometry(geometry)
        super().showEvent(event)

    def closeEvent(self, event):
        if self.app_prefs_name:
            settings = Qt.QSettings('zplab', self.app_prefs_name)
            settings.setValue('main_window_geometry', self.saveGeometry())
        super().closeEvent(event)

    @property
    def layers(self):
        """If you wish to replace the current .layers, it may be done by assigning to this property.  For example:
        import freeimage
        from ris_widget.layer import Layer
        rw.layers = [Layer(freeimage.read(str(p))) for p in pathlib.Path('./').glob('*.png')]."""
        return self.layer_stack.layers

    @layers.setter
    def layers(self, v):
        self.layer_stack.layers = v

    @property
    def focused_layer(self):
        """rw.focused_layer: A convenience property equivalent to rw.layer_stack.focused_layer."""
        return self.layer_stack.focused_layer

    @focused_layer.setter
    def focused_layer(self, v):
        self.layer_stack.focused_layer = v

    @property
    def layer(self):
        """rw.layer: A convenience property equivalent to rw.layers[0] and rw.layer_stack.layers[0], with minor differences:
        * If rw.layers is None: Querying rw.layer causes rw.layers to be set to a LayerList containing a single empty Layer which is returned,
        while assigning to rw.layer causes rw.layers to be set to a LayerList containing the thing assigned (wrapped in a Layer as needed).
        * If len(rw.layers) == 0: Querying rw.layer causes a new Layer to be inserted at rw.layers[0] and returned, while assigning to
        rw.layer causes the assigned thing to be inserted at rw.layers[0] (wrapped in a Layer as needed)."""
        if len(self.layers) == 0:
            self.layers.append(layer.Layer())
        return self.layers[0]

    @layer.setter
    def layer(self, v):
        if len(self.layers) == 0:
            self.layers.append(v)
        else:
            self.layers[0] = v

    @property
    def image(self):
        """rw.image: A Convenience property exactly equivalent to rw.layer.image, and equivalent to
        rw.layer_stack[0].image with a minor difference: if len(rw.layer_stack) == 0, a query of rw.image
        returns None rather than raising an exception, and an assignment to it in this scenario is
        equivalent to rw.layer_stack.insert(0, Layer(v))."""
        return self.layer.image

    @image.setter
    def image(self, v):
        self.layer.image = v

    @property
    def mask(self):
        return self.layer_stack.imposed_image_mask

    @mask.setter
    def mask(self, v):
        self.layer_stack.imposed_image_mask = v

    def _update_flipbook_visibility(self):
        visible = self.flipbook_dock_widget.isVisible()
        has_pages = len(self.flipbook.pages) > 0
        if has_pages and not visible:
            self.flipbook_dock_widget.show()
        elif not has_pages and visible:
            self.flipbook_dock_widget.hide()

    def _update_layer_stack_visibility(self):
        visible = self.layer_table_dock_widget.isVisible()
        multilayer = len(self.layers) > 1
        if multilayer and not visible:
            self.layer_table_dock_widget.show()
        # don't autohide...
        # elif not multilayer and visible:
        #     self.layer_table_dock_widget.hide()

    def _image_view_zoom_changed(self, zoom):
        zoom = format(100*zoom, '.1f').rstrip('0').rstrip('.') + '%'
        self.zoom_editor.setText(zoom)

    def _on_zoom_editing_finished(self):
        zoom = self.zoom_editor.text().rstrip('%')
        try:
            zoom = float(zoom) / 100
        except ValueError:
            # reset the text to the current zoom
            self._image_view_zoom_changed(self.image_view.zoom)
            self.zoom_editor.setFocus()
            self.zoom_editor.selectAll()
        else:
            self.image_view.zoom = zoom

    def _on_reset_min_max(self):
        layer = self.focused_layer
        if layer is not None:
            del layer.min
            del layer.max

    def _on_reset_gamma(self):
        layer = self.focused_layer
        if layer is not None:
            del layer.gamma

    def _on_toggle_auto_min_max(self):
        layer = self.focused_layer
        if layer is not None:
            layer.auto_min_max = not layer.auto_min_max

    def _on_snapshot_action(self):
        # if sys.platform == 'darwin':
        #     # Onn some versions of PyQt, IPython, and OS X, the Qt event loop intergration can cause the
        #     # native  file save dialog to be dismissed just as it appears. Uncomment if this problem returns
        #     options = Qt.QFileDialog.DontUseNativeDialog
        # else:
        #     options = Qt.QFileDialog.Option()
        # fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Snapshot',
        #             filter='Images (*.png *.jpg *.tiff *.tif)', options=options)

        fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Snapshot', filter='Images (*.png *.jpg *.tiff *.tif)')

        if fn:
            freeimage.write(self.image_view.snapshot(), fn)

    def _on_save_layer_property_stack(self):
        # if sys.platform == 'darwin':
        #     # On some versions of PyQt, IPython, and OS X, the Qt event loop intergration can cause the
        #     # native  file save dialog to be dismissed just as it appears. Uncomment if this problem returns
        #     options = Qt.QFileDialog.DontUseNativeDialog
        # else:
        #     options = Qt.QFileDialog.Option()
        # fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Layer Property Stack',
        #             filter='JSON (*.json *.jsn)', options=options)

        fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Layer Property Stack', filter='JSON (*.json *.jsn)')
        if fn:
            with open(fn, 'w') as f:
                f.write(self.layers.to_json())

    def _on_load_layer_property_stack(self):
        # if sys.platform == 'darwin':
        #     # On some versions of PyQt, IPython, and OS X, the Qt event loop intergration can cause the
        #     # native  file save dialog to be dismissed just as it appears. Uncomment if this problem returns
        #     options = Qt.QFileDialog.DontUseNativeDialog
        # else:
        #     options = Qt.QFileDialog.Option()
        # fn, _ = Qt.QFileDialog.getOpenFileName(self, 'Load Layer Property Stack',
        #             filter='JSON (*.json *.jsn)', options=options)

        fn, _ = Qt.QFileDialog.getOpenFileName(self, 'Load Layer Property Stack', filter='JSON (*.json *.jsn)')
        if fn:
            with open(fn) as f:
                l = layer_stack.LayerList.from_json(f.read())
                if l is not None:
                    self.layers = l

class ProxyProperty(property):
    def __init__(self, name, owner_name, owner_type):
        self.owner_name = owner_name
        self.proxied_property = getattr(owner_type, name)
        self.__doc__ = getattr(owner_type, '__doc__')

    def __get__(self, obj, _=None):
        if obj is None:
            return self.proxied_property
        return self.proxied_property.fget(getattr(obj, self.owner_name))

    def __set__(self, obj, v):
        self.proxied_property.fset(getattr(obj, self.owner_name), v)

    def __delete__(self, obj):
        self.proxied_property.fdel(getattr(obj, self.owner_name))

class RisWidget:
    def __init__(self, window_title='RisWidget'):
        self.qt_object = RisWidgetQtObject(app_prefs_name='RisWidget', window_title=window_title)
        qo = self.qt_object
        self.image_view_change_signal = qo.image_view_change_signal
        self.flipbook = qo.flipbook
        self.image_scene = qo.image_scene
        self.image_view = qo.image_view
        self.image_viewport = qo.image_scene.viewport_rect_item
        self.layer_stack = qo.layer_stack
        self.show = qo.show
        self.hide = qo.hide
        self.close = qo.close
        self.add_image_files_to_flipbook = self.flipbook.add_image_files
        self.snapshot = self.qt_object.image_view.snapshot
        self.actions = {}
        self.show()

    def add_action(self, name, shortcut_key, function):
        action = Qt.QAction(name, self.qt_object)
        action.setShortcut(shortcut_key)
        action.triggered.connect(function)
        self.qt_object.addAction(action)
        self.actions[name] = action
        return action

    def update(self):
        """Calling this method on the main thread updates all Qt widgets immediately, without requiring
        you to return from the current function or exit from the current loop.

        For example, the following code will create and show a RisWidget that appears to be non-responsive
        for ten seconds, after which a white square is displayed:

        import numpy
        from ris_widget.ris_widget import RisWidget; rw = RisWidget()
        import time
        rw.image = numpy.zeros((100,100), dtype=numpy.uint8)
        for intensity in numpy.linspace(0,255,100).astype(numpy.uint8):
            time.sleep(0.1)
            rw.image.data[:] = intensity
            rw.image.refresh()

        Adding an rw.update() call to the loop fixes this:

        import numpy
        from ris_widget.ris_widget import RisWidget; rw = RisWidget()
        import time
        rw.image = numpy.zeros((100,100), dtype=numpy.uint8)
        for intensity in numpy.linspace(0,255,100).astype(numpy.uint8):
            rw.update()
            time.sleep(0.1)
            rw.image.data[:] = intensity
            rw.image.refresh()
        """
        Qt.QApplication.processEvents()

    image = ProxyProperty('image', 'qt_object', RisWidgetQtObject)
    layer = ProxyProperty('layer', 'qt_object', RisWidgetQtObject)
    focused_layer = ProxyProperty('focused_layer', 'qt_object', RisWidgetQtObject)
    layers = ProxyProperty('layers', 'qt_object', RisWidgetQtObject)
    mask = ProxyProperty('mask', 'qt_object', RisWidgetQtObject)
    # It is not easy to spot the pages property of a flipbook amongst the many possibilities visibile in dir(Flipbook).  So,
    # although flipbook_pages saves no characters compared to flipbook.pages, flipbook_pages is nice to have.
    flipbook_pages = ProxyProperty('pages', 'flipbook', flipbook.Flipbook)

if __name__ == '__main__':
    import sys
    app = Qt.QApplication(sys.argv)
    rw = RisWidget()
    rw.show()
    app.exec_()
