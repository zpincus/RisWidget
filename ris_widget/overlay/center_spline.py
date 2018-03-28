# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
import numpy

from zplib.curve import interpolate
from zplib.image import resample

from .. import shared_resources
from . import base

class CenterSpline(base.RWGeometryItemMixin, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    SPLINE_POINTS = 250
    SMOOTH_BASE = 8
    SMOOTH_MIN = 1
    SMOOTH_MAX = 256

    BANDWIDTH = 10

    def __init__(self, ris_widget, pen=None, geometry=None):
        self._smoothing = self.SMOOTH_BASE
        self._tck = None
        self.warping = False
        self.drawing = False
        self.fine_warp = False # if True, warp bandwidth is halved
        super().__init__(ris_widget, pen, geometry)
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable)

    @property
    def geometry(self):
        return self._tck

    @geometry.setter
    def geometry(self, tck):
        self.setSelected(False)
        self._set_tck(tck)
        self._update_points()

    def _set_tck(self, tck):
        self.drawing = False
        self._tck = tck
        self._update_path()
        self._geometry_changed()

    def _update_path(self):
        self.path = Qt.QPainterPath()
        tck = self._tck
        if tck is not None:
            bezier_elements = interpolate.spline_to_bezier(tck)
            self.path.moveTo(*bezier_elements[0][0])
            for (sx, sy), (c1x, c1y), (c2x, c2y), (ex, ey) in bezier_elements:
                self.path.cubicTo(c1x, c1y, c2x, c2y, ex, ey)
        self.setPath(self.path)

    def _update_points(self):
        if self._tck is None:
            self._points = []
        else:
            self._points = self.evaluate_tck()

    def _modify_smoothing(self, decrease):
        if decrease:
            self._smoothing = max(self._smoothing / 2, self.SMOOTH_MIN)
        else:
            self._smoothing = min(self._smoothing * 2, self.SMOOTH_MAX)
        if self._tck is not None:
            self._generate_tck_from_points()

    def _generate_tck_from_points(self):
        if len(self._points) > 4:
            tck = self.calculate_tck(self._points)
        else:
            tck = None
        self._set_tck(tck)

    def calculate_tck(self, points):
        return interpolate.fit_spline(points, smoothing=self._smoothing * len(points))

    def evaluate_tck(self, derivative=0):
        return interpolate.spline_interpolate(self._tck, num_points=self.SPLINE_POINTS, derivative=derivative)

    def start_drawing(self):
        self.drawing = True
        self.display_pen.setStyle(Qt.Qt.DotLine)
        self.setPen(self.display_pen)
        self._last_pos = None
        self.path = Qt.QPainterPath()
        self.setPath(self.path)

    def _stop_drawing(self):
        self._points = numpy.array(self._points)
        self.display_pen.setStyle(Qt.Qt.SolidLine)
        self.setPen(self.display_pen)
        self._generate_tck_from_points()
        self._update_points()
        self.drawing = False

    def _add_point(self, pos):
        x, y = pos.x(), pos.y()
        last = self._last_pos
        if last is not None and (x - last[0])**2 + (y - last[1])**2 < 36:
            return
        self._points.append((x, y))
        if last is None:
            self.path.moveTo(pos)
        else:
            self.path.lineTo(pos)
        self._last_pos = x, y
        self.setPath(self.path)

    def _start_warp(self, pos):
        self._warp_start = numpy.array([pos.x(), pos.y()])
        self._warp_points = self._points
        self._warp_distances = numpy.sqrt(((self._warp_start - self._points)**2).sum(axis=1))
        self._warp_bandwidth = self._tck[0][-1] / self.BANDWIDTH # tck[0][-1] is approximate spline length

    def _warp_spline(self, pos):
        self._last_pos = pos
        end = numpy.array([pos.x(), pos.y()])
        delta = end - self._warp_start
        bandwidth_factor = 0.5 if self.fine_warp else 1
        bandwidth = self._warp_bandwidth * bandwidth_factor
        warp_coefficients = numpy.exp(-(self._warp_distances/bandwidth)**2)
        displacements = numpy.outer(warp_coefficients, delta)
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self._points = self._warp_points + displacements
        self._generate_tck_from_points()

    def _extend_endpoint(self, pos):
        new_end = numpy.array([pos.x(), pos.y()])
        old_ends = self._points[[0,-1]]
        dists = ((old_ends - new_end)**2).sum(axis=1)
        if dists[0] < dists[1]:
            new_points = [[new_end], self._points]
        else:
            new_points = [self._points, [new_end]]
        self._points = numpy.concatenate(new_points)
        self._generate_tck_from_points()
        self._update_points()

    def reverse_spline(self):
        self._set_tck(interpolate.reverse_spline(self._tck))
        self._points = self._points[::-1]

    def smooth(self):
        self._update_points()
        self._generate_tck_from_points()

    def sceneEventFilter(self, watched, event):
        tck, drawing = self._tck, self.drawing
        if drawing and event.type() in {Qt.QEvent.GraphicsSceneMousePress, Qt.QEvent.GraphicsSceneMouseMove}:
            self._add_point(event.pos())
            return True
        elif drawing and event.type() == Qt.QEvent.GraphicsSceneMouseRelease:
            self._stop_drawing()
            return True
        elif tck is not None and event.type() == Qt.QEvent.GraphicsSceneMouseDoubleClick:
            self._extend_endpoint(event.pos())
            return True
        elif event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Shift:
            self.fine_warp = True
            if self.warping:
                self._warp_spline(self._last_pos)
            return True
        elif event.type() == Qt.QEvent.KeyRelease and event.key() == Qt.Qt.Key_Shift:
            self.fine_warp = False
            if self.warping:
                self._warp_spline(self._last_pos)
            return True
        elif tck is None and not drawing and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Escape:
            self.start_drawing()
            return True
        elif tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_R:
            self.reverse_spline()
            return True
        elif tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_S:
            self.smooth()
            return True
        elif event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_F:
            self._modify_smoothing(decrease=(event.modifiers() & Qt.Qt.ShiftModifier))
            return True
        return super().sceneEventFilter(watched, event)

    def mousePressEvent(self, event):
        self._start_warp(event.pos())

    def mouseMoveEvent(self, event):
        self.warping = True
        self._warp_spline(event.pos())

    def mouseReleaseEvent(self, event):
        if self.warping:
            self.warping = False
            self._geometry_changed()
        else:
            # allow the rest of the release event mechanism to work
            super().mouseReleaseEvent(event)