from PyQt5 import Qt

from .qwidgets import layer_stack_painter
from .qwidgets import annotator

class _RWDockWidget(Qt.QDockWidget):
    def __init__(self, rw, name):
        rw = rw.qt_object
        super().__init__(name, rw)
        self.setAllowedAreas(Qt.Qt.RightDockWidgetArea | Qt.Qt.LeftDockWidgetArea)
        self.setFeatures(
            Qt.QDockWidget.DockWidgetClosable | Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        rw.addDockWidget(Qt.Qt.RightDockWidgetArea, self)
        self._init_widget(rw)
        self.setWidget(self.widget)
        rw.dock_widget_visibility_toolbar.addAction(self.toggleViewAction())
        self.show()


class Painter(_RWDockWidget):
    def __init__(self, rw):
        super().__init__(rw, 'Painter')

    def _init_widget(self, rw):
        self.widget = layer_stack_painter.LayerStackPainter(rw, parent=self)


class Annotator(_RWDockWidget):
    __doc__ = annotator.Annotator.__doc__

    def __init__(self, rw, fields):
        self.fields = fields
        super().__init__(rw, 'Annotator')
        self.update_fields = self.widget.update_fields

    def _init_widget(self, rw):
        self.widget = annotator.Annotator(rw, self.fields, parent=self)

    @property
    def all_annotations(self):
        return self.widget.all_annotations

    @all_annotations.setter
    def all_annotations(self, v):
        self.widget.all_annotations = v

    @property
    def current_annotations(self):
        return self.widget.current_annotations


