# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from . import ris_widget

class LinkedRisWidget(ris_widget.RisWidgetBase):
    def __init__(self, src_rw, link_zoom=False, parent=None):
        super().__init__(parent=parent)
        src_rw.layer_stack.layer_focus_changed.connect(self._on_src_layer_focus_changed)
        self._on_src_layer_focus_changed(src_rw.layer_stack, None, src_rw.focused_layer)
        if link_zoom:
            self.image_view.allow_wheel_zoom = False
            src_rw.image_view.zoom_changed.connect(self._src_zoom_changed)

    def _on_src_layer_changed(self, layer):
        dst_layer = self.layers[0]
        dst_layer.min = layer.min
        dst_layer.max = layer.max
        dst_layer.gamma = layer.gamma

    def _on_src_layer_focus_changed(self, layer_stack, old_focused_layer, focused_layer):
        if old_focused_layer is not None:
            old_focused_layer.changed.disconnect(self._on_src_layer_changed)
        if focused_layer is not None:
            focused_layer.changed.connect(self._on_src_layer_changed)
            self._on_src_layer_changed(focused_layer)

    def _src_zoom_changed(self, zoom):
        self.image_view.zoom = zoom


def split_view_rw(rw):
    rw.alt_view = LinkedRisWidget(rw, parent=rw)
    rw.splitter = Qt.QSplitter(Qt.Qt.Vertical)
    rw.splitter.addWidget(rw.qt_object.takeCentralWidget())
    rw.splitter.setStretchFactor(0, 45)
    rw.splitter.setCollapsible(0, False)
    rw.splitter.addWidget(rw.alt_view.image_view)
    rw.splitter.setStretchFactor(1, 10)
    rw.qt_object.setCentralWidget(rw.splitter)
