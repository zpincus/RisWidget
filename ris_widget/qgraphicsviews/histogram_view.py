# This code is licensed under the MIT License (see LICENSE file for details)

from . import base_view
from PyQt5 import Qt

class HistogramView(base_view.BaseView):
    @classmethod
    def make_histogram_view_and_frame(cls, base_scene, parent=None):
        histogram_frame = Qt.QFrame(parent)
        histogram_frame.setMinimumSize(Qt.QSize(120, 60))
        histogram_frame.setFrameShape(Qt.QFrame.StyledPanel)
        histogram_frame.setFrameShadow(Qt.QFrame.Sunken)
        histogram_frame.setLayout(Qt.QHBoxLayout())
        histogram_frame.layout().setSpacing(0)
        histogram_frame.layout().setContentsMargins(Qt.QMargins(0,0,0,0))
        histogram_view = cls(base_scene, histogram_frame)
        histogram_frame.layout().addWidget(histogram_view)
        return histogram_view, histogram_frame

    def _on_resize(self, size):
        self.resetTransform()
        self.scale(size.width(), size.height())
