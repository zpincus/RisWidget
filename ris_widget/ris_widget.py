# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from . import shared_resources
from . import internal_util
from . import layer_stack
from . import histogram_mask
from . import dock_widgets
from . import qgraphicsscenes
from .qwidgets import flipbook
from .qwidgets import fps_display
from .qwidgets import layer_table
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

ICON_RESOURCE_PATH = __name__, 'icon.svg'

class RisWidgetBase:
    def __init__(self, subwidget_parent=None):
        shared_resources.init_qapplication(ICON_RESOURCE_PATH)
        self.layer_stack = layer_stack.LayerStack()
        self.image_scene = qgraphicsscenes.ImageScene(self.layer_stack, subwidget_parent)
        self.image_view = image_view.ImageView(self.image_scene, subwidget_parent)

    @property
    def layers(self):
        """Convenience property equivalent to layer_stack.layers. Assigning to layers
        is smart: if images are provided, any existing layer properties will be retained.
        To clear the layers and start afresh do:
        layers.clear()
        layers.extend([img1, img2])
        """
        return self.layer_stack.layers

    @layers.setter
    def layers(self, new_layers):
        self.layer_stack.layers = new_layers

    @property
    def layer(self):
        """layer: A convenience property equivalent to layers[0] and layer_stack.layers[0]"""
        return self.layers[0]

    @layer.setter
    def layer(self, v):
        self.layers[0] = v

    @property
    def image(self):
        """image: A Convenience property exactly equivalent to layer.image, and equivalent to
        layer_stack[0].image."""
        return self.layer.image

    @image.setter
    def image(self, v):
        self.layer.image = v

    def input(self, message=''):
        """Replacement for python-builtin input() which will still allow a RisWidget
        to update while waiting for input.
        """
        import IPython
        import prompt_toolkit
        from pkg_resources import parse_version
        inputhook = IPython.get_ipython().inputhook
        if parse_version(prompt_toolkit.__version__) < parse_version('2'):
            args = dict(eventloop=prompt_toolkit.shortcuts.create_eventloop(inputhook))
        else:
            args = dict(inputhook=inputhook)
        return prompt_toolkit.prompt(message, **args)

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

    def run(self):
        """Run the Qt application event loop in a way that it can still be interrupted
        with control-c. Can be used to hand over control to the event loop permanently
        (as when running as a standalone application), or temporarily from IPython
        while still allowing control-c to return to the regular interpreter."""
        shared_resources.run_qapplication()

class RisWidgetQtObject(RisWidgetBase, Qt.QMainWindow):
    def __init__(self, app_prefs_name='RisWidget', window_title='RisWidget', parent=None):
        RisWidgetBase.__init__(self, subwidget_parent=self)
        Qt.QMainWindow.__init__(self, parent)
        # below is necessary to quit cleanly, especially with QGraphicsItems onscreen and similar:
        # if Qt is shutting down while the window is still open, then python code can get called
        # after the backing Qt C++ objects have been deleted.
        shared_resources.QAPPLICATION.aboutToQuit.connect(self.close)

        self.app_prefs_name = app_prefs_name
        self._shown = False
        if window_title is not None:
            self.setWindowTitle(window_title)
        self.setAcceptDrops(True)
        self._init_scenes_and_views()
        self._init_flipbook()
        self._init_actions()
        self._init_toolbars()
        self._init_menus()

    def _init_scenes_and_views(self):
        self.setCentralWidget(self.image_view)

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
        # setting the selection model isn't part of the layer_stack constructor
        # because otherwise there would be a circular dependency
        self.layer_stack.set_selection_model(self.layer_table_view.selectionModel())
        self.layer_table_model.setParent(self.layer_table_view)
        self.layer_table_model.rowsInserted.connect(self._update_layer_stack_visibility)
        self.layer_table_model.rowsRemoved.connect(self._update_layer_stack_visibility)

        self.layer_table_dock_widget = Qt.QDockWidget('Layer Stack', self)
        self.layer_table_dock_widget.setWidget(self.layer_table_view)
        self.layer_table_dock_widget.setAllowedAreas(Qt.Qt.AllDockWidgetAreas)
        self.layer_table_dock_widget.setFeatures(Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetVerticalTitleBar)
        self.addDockWidget(Qt.Qt.TopDockWidgetArea, self.layer_table_dock_widget)
        self.layer_table_dock_widget.hide()

        self.histogram_scene = qgraphicsscenes.HistogramScene(self.layer_stack, self)
        self.histogram_dock_widget = Qt.QDockWidget('Histogram', self)
        self.histogram_view, self._histogram_frame = histogram_view.HistogramView.make_histogram_view_and_frame(self.histogram_scene, self.histogram_dock_widget)
        self.histogram_dock_widget.setWidget(self._histogram_frame)
        self.histogram_dock_widget.setAllowedAreas(Qt.Qt.BottomDockWidgetArea | Qt.Qt.TopDockWidgetArea)
        self.histogram_dock_widget.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable |
            Qt.QDockWidget.DockWidgetMovable | Qt.QDockWidget.DockWidgetVerticalTitleBar)
        self.addDockWidget(Qt.Qt.BottomDockWidgetArea, self.histogram_dock_widget)

        self.fps_display_dock_widget = Qt.QDockWidget('FPS', self)
        self.fps_display = fps_display.FPSDisplay(self.image_scene.layer_stack_item.new_image_painted)
        self.fps_display_dock_widget.setWidget(self.fps_display)
        self.fps_display_dock_widget.setAllowedAreas(Qt.Qt.AllDockWidgetAreas)
        self.fps_display_dock_widget.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.Qt.RightDockWidgetArea, self.fps_display_dock_widget)
        self.fps_display_dock_widget.hide()

    def _init_actions(self):
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
        self.flipbook_dock_widget.hide()
        # Make the flipbook deal with drop events
        self.dragEnterEvent = self.flipbook.pages_view.dragEnterEvent
        self.dragMoveEvent = self.flipbook.pages_view.dragMoveEvent
        self.dropEvent = self.flipbook.pages_view.dropEvent

    def _init_toolbars(self):
        self.main_view_toolbar = self.addToolBar('Image')
        self.zoom_editor = Qt.QLineEdit()
        self.zoom_editor.setAlignment(Qt.Qt.AlignCenter)
        w = self.zoom_editor.fontMetrics().boundingRect('0000.0%').width()
        self.zoom_editor.setFixedWidth(w + 14)
        self.zoom_editor.editingFinished.connect(self._on_zoom_editing_finished)
        self.zoom_editor.setAlignment(Qt.Qt.AlignCenter)
        self.main_view_toolbar.addWidget(self.zoom_editor)
        self.image_view.zoom_changed.connect(self._image_view_zoom_changed)
        self.main_view_toolbar.addAction(self.image_view.zoom_to_fit_action)
        self.main_view_toolbar.addAction(self.layer_stack_reset_curr_min_max_action)
        self.main_view_toolbar.addAction(self.layer_stack_reset_curr_gamma_action)
        self.main_view_toolbar.addAction(self.layer_stack.auto_min_max_all_action)
        self.main_view_toolbar.addAction(self.layer_stack.solo_layer_mode_action)
        if freeimage is not None:
            self.main_view_toolbar.addAction(self.snapshot_action)
        self.dock_widget_visibility_toolbar = self.addToolBar('Dock Widget Visibility')
        self.dock_widget_visibility_toolbar.addAction(self.layer_table_dock_widget.toggleViewAction())
        self.dock_widget_visibility_toolbar.addAction(self.histogram_dock_widget.toggleViewAction())
        self.dock_widget_visibility_toolbar.addAction(self.flipbook_dock_widget.toggleViewAction())

    def _init_menus(self):
        mb = self.menuBar()
        f = mb.addMenu('File')
        f.addAction(self.layer_property_stack_save_action)
        f.addAction(self.layer_property_stack_load_action)
        v = mb.addMenu('View')
        v.addAction(self.fps_display_dock_widget.toggleViewAction())
        self._hist_mask = histogram_mask.HistogramMask(self, v)

    def showEvent(self, event):
        if self.app_prefs_name and not self._shown:
            self._shown = True
            settings = Qt.QSettings('zplab', self.app_prefs_name)
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
    def focused_layer(self):
        """focused_layer: A convenience property equivalent to rw.layer_stack.focused_layer."""
        return self.layer_stack.focused_layer

    @focused_layer.setter
    def focused_layer(self, v):
        self.layer_stack.focused_layer = v

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
        fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Snapshot', filter='Images (*.png *.jpg *.tiff *.tif)')

        if fn:
            freeimage.write(self.image_view.snapshot(), fn)

    def _on_save_layer_property_stack(self):
        fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Layer Property Stack', filter='JSON (*.json *.jsn)')
        if fn:
            with open(fn, 'w') as f:
                f.write(self.layers.to_json())

    def _on_load_layer_property_stack(self):
        fn, _ = Qt.QFileDialog.getOpenFileName(self, 'Load Layer Property Stack', filter='JSON (*.json *.jsn)')
        if fn:
            with open(fn) as f:
                layers = layer_stack.LayerList.from_json(f.read())
                if layers is not None:
                    self.layers = layers

class RisWidget:
    def __init__(self, window_title='RisWidget'):
        self.qt_object = RisWidgetQtObject(window_title=window_title)
        qo = self.qt_object
        self.flipbook = qo.flipbook
        self.image_scene = qo.image_scene
        self.image_view = qo.image_view
        self.image_viewport = qo.image_scene.viewport_rect_item
        self.layer_stack = qo.layer_stack
        self.show = qo.show
        self.hide = qo.hide
        self.close = qo.close
        self.run = qo.run
        self.update = qo.update
        self.input = qo.input
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

    def add_painter(self):
        if hasattr(self, 'painter'):
            raise RuntimeError('painter already added')
        self._painter_widget, self.painter = dock_widgets.Painter.add_dock_widget(self.qt_object)

    def add_annotator(self, fields):
        if hasattr(self, 'annotator'):
            raise RuntimeError('annotator already added')
        self._annotator_widget, self.annotator = dock_widgets.Annotator.add_dock_widget(self.qt_object, fields=fields)

    image = internal_util.ProxyProperty('qt_object', RisWidgetQtObject.image)
    layer = internal_util.ProxyProperty('qt_object', RisWidgetQtObject.layer)
    focused_layer = internal_util.ProxyProperty('qt_object', RisWidgetQtObject.focused_layer)
    layers = internal_util.ProxyProperty('qt_object', RisWidgetQtObject.layers)
    # It is not easy to spot the pages property of a flipbook amongst the many possibilities visibile in dir(Flipbook).  So,
    # although flipbook_pages saves no characters compared to flipbook.pages, flipbook_pages is nice to have.
    flipbook_pages = internal_util.ProxyProperty('flipbook', flipbook.Flipbook.pages)

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="zplab image viewer")
    parser.add_argument('images', nargs="*", metavar='image', help='image files to open')
    default_desktop_dir = '/usr/local/share/applications'
    parser.add_argument('--install-desktop-file', nargs='?', metavar='dir', const=default_desktop_dir,
         help=f'install linux .desktop file to specified directory (or, if not specified, {default_desktop_dir})')

    args = parser.parse_args(argv)
    if args.install_desktop_file:
        from . import install_desktop_file
        install_desktop_file.install_desktop_file(args.install_desktop_file)
    else:
        ris_widget = RisWidget()
        ris_widget.add_image_files_to_flipbook(args.images)
        ris_widget.run()

if __name__ == '__main__':
    main()
