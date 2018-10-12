# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .qwidgets import layer_stack_painter
from .qwidgets import annotator

class _RWDockWidget(Qt.QDockWidget):
    @classmethod
    def add_dock_widget(cls, ris_widget, **widget_kws):
        dock_widget = cls(ris_widget, **widget_kws)
        return dock_widget, dock_widget.widget

    def __init__(self, ris_widget, **widget_kws):
        super().__init__(self.name, ris_widget)
        self.setAllowedAreas(Qt.Qt.RightDockWidgetArea | Qt.Qt.LeftDockWidgetArea)
        self.setFeatures(Qt.QDockWidget.DockWidgetClosable |
            Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        ris_widget.addDockWidget(Qt.Qt.RightDockWidgetArea, self)
        self.widget = self.widget_class(ris_widget, parent=ris_widget, **widget_kws)
        self.setWidget(self.widget)
        ris_widget.dock_widget_visibility_toolbar.addAction(self.toggleViewAction())
        self.show()


class Painter(_RWDockWidget):
    name = 'Painter'
    widget_class = layer_stack_painter.LayerStackPainter


class Annotator(_RWDockWidget):
    name = 'Annotator'
    widget_class = annotator.Annotator
