# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from zplib.curve import interpolate

from .. import shared_resources
from . import polyline

class Spline(polyline.Polyline):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, smoothing=10, geometry=None):
        self._smoothing = smoothing
        super().__init__(ris_widget, pen, geometry)

    @property
    def smoothing(self):
        return self._smoothing

    @smoothing.setter
    def smoothing(self, value):
        self._smoothing = value
        self._generate_path()

    def _generate_path_from_positions(self, positions):
        if len(positions) < 4:
            return super()._generate_path_from_positions(positions)
        points = [(pos.x(), pos.y()) for pos in positions]
        self.tck = interpolate.fit_spline(points, smoothing=self._smoothing*len(points))
        bezier_elements = interpolate.spline_to_bezier(self.tck)
        path = Qt.QPainterPath()
        path.moveTo(*bezier_elements[0][0])
        for (sx, sy), (c1x, c1y), (c2x, c2y), (ex, ey) in bezier_elements:
            path.cubicTo(c1x, c1y, c2x, c2y, ex, ey)
        return path

    def sceneEventFilter(self, watched, event):
        if event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_S:
            if event.modifiers() & Qt.Qt.ShiftModifier:
                self.smoothing *= 1.5
            else:
                self.smoothing /= 1.5
            return True
        return super().sceneEventFilter(watched, event)
