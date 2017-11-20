# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from . import ris_widget

class LinkedRisWidget(ris_widget.RisWidgetBase):
    def __init__(self, parent=None):
        ris_widget.RisWidgetBase.__init__(self, parent=self)

    def link(self, src_rw, src_layer_idx=0, dst_layer_idx=0):
        self.link_scaling(src_rw.layers[src_layer_idx], dst_layer_idx)
        self.link_zoom(src_rw)

    def link_scaling(self, src_layer, dst_layer_idx=0):
        def on_layer_changed(layer):
            dst_layer = self.layers[dst_layer_idx]
            dst_layer.min = layer.min
            dst_layer.max = layer.max
            dst_layer.gamma = layer.gamma
        src_layer.changed.connect(on_layer_changed)

    def link_zoom(self, src_rw):
        self.image_view.allow_wheel_zoom = False
        src_rw.image_view.zoom_changed.connect(self._src_zoom_changed)

    def _src_zoom_changed(self, zoom):
        self.image_view.zoom = zoom

def split_view_rw(rw, src_layer_idx=0, dst_layer_idx=0):
    rw.alt_view = LinkedRisWidget(parent=rw)
    rw.splitter = Qt.QSplitter(Qt.Qt.Vertical)
    rw.splitter.addWidget(rw.qt_object.takeCentralWidget())
    rw.splitter.setStretchFactor(0, 45)
    rw.splitter.setCollapsible(0, False)
    rw.splitter.addWidget(rw.alt_view.image_view)
    rw.splitter.setStretchFactor(1, 10)
    rw.alt_view.link(rw, src_layer_idx, dst_layer_idx)
    rw.qt_object.setCentralWidget(rw.splitter)
