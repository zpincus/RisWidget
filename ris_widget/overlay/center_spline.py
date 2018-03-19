# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
import numpy

from zplib.curve import interpolate
from zplib.image import resample

from .. import shared_resources
from . import base

class CenterSpline(base.RWGeometryItemMixin, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    SPLINE_POINTS = 400
    SMOOTH_BASE = 8
    BANDWIDTH = 20

    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None):
        self._drawing = False
        self._smoothing = 1
        self._tck = None
        self._points = []
        self._on_reversed = None
        super().__init__(ris_widget, color, geometry)
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
        tck = self._tck
        if tck is not None:
            self._points = interpolate.spline_interpolate(tck, num_points=self.SPLINE_POINTS)
        else:
            self._points = []

    def _modify_smoothing(self, increase):
        if increase:
            self._smoothing = min(self._smoothing * 2, 32)
        else:
            self._smoothing = max(self._smoothing / 2, 0.25)
        if self._tck is not None:
            self._generate_tck_from_points()

    def _generate_tck_from_points(self):
        l = len(self._points)
        if l > 4:
            tck = interpolate.fit_spline(self._points, smoothing=self._smoothing * self.SMOOTH_BASE * l)
        else:
            tck = None
        self._set_tck(tck)

    def _start_drawing(self):
        self._drawing = True
        self.display_pen.setStyle(Qt.Qt.DotLine)
        self.setPen(self.display_pen)
        self._last_pos = None
        self.path = Qt.QPainterPath()
        self.setPath(self.path)

    def _stop_drawing(self):
        self.display_pen.setStyle(Qt.Qt.SolidLine)
        self.setPen(self.display_pen)
        self._generate_tck_from_points()
        # _generate_tck_from_points might act differently at the end of drawing
        # (in a subclass), so set _drawing False only at end.
        self._drawing = False

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

    def _warp_spline(self, pos, bandwidth_factor):
        end = numpy.array([pos.x(), pos.y()])
        delta = end - self._warp_start
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

    def _reverse_spline(self):
        self._set_tck(interpolate.reverse_spline(self._tck))
        self._points = self._points[::-1]
        if self._on_reversed is not None:
            self._on_reversed()

    def sceneEventFilter(self, watched, event):
        tck, drawing = self._tck, self._drawing
        if drawing and event.type() in {Qt.QEvent.GraphicsSceneMousePress, Qt.QEvent.GraphicsSceneMouseMove}:
            self._add_point(event.pos())
            return True
        elif drawing and event.type() == Qt.QEvent.GraphicsSceneMouseRelease:
            self._stop_drawing()
            return True
        elif tck is not None and event.type() == Qt.QEvent.GraphicsSceneMousePress and event.modifiers() & Qt.Qt.ShiftModifier:
            self._extend_endpoint(event.pos())
            return True
        elif tck is None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Shift:
            if not drawing:
                self._start_drawing()
            else:
                self._stop_drawing()
            return True
        elif tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_R:
            self._reverse_spline()
            return True
        elif tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_D:
            self._update_points()
            self._generate_tck_from_points()
            return True
        elif event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_S:
            self._modify_smoothing(increase=(event.modifiers() & Qt.Qt.ShiftModifier))
            return True
        return super().sceneEventFilter(watched, event)

    def mousePressEvent(self, event):
        self._start_warp(event.pos())

    def mouseMoveEvent(self, event):
        bandwidth_factor = 1
        if event.modifiers() & Qt.Qt.ShiftModifier:
            bandwidth_factor = 2
        self._warp_spline(event.pos(), bandwidth_factor)

class WarpedViewCenterSplineListener(Qt.QGraphicsObject):
    def __init__(self, center_spline, warped_view):
        self.warped_view = warped_view
        layer_stack_item = warped_view.image_scene.layer_stack_item
        super().__init__(layer_stack_item)
        self.setFlag(Qt.QGraphicsItem.ItemHasNoContents)
        layer_stack_item.installSceneEventFilter(self)
        self.center_spline = center_spline
        center_spline.geometry_change_callbacks.append(self._update_warped_view)
        center_spline.rw.layer_stack.focused_image_changed.connect(self._update_warped_view)
        self._on_focused_image_changed(center_spline.rw.layer_stack.focused_image)

    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    def type(self):
        return self.QGRAPHICSITEM_TYPE

    def boundingRect(self):
        return Qt.QRectF()

    def remove(self):
        self.parentItem().removeSceneEventFilter(self)
        self.center_spline.rw.layer_stack.focused_image_changed.disconnect(self._update_warped_view)
        self.center_spline.geometry_change_callbacks.remove(self._update_warped_view)

    def _update_warped_view(self, _, order=0):
        # dummy parameter _ will either be image if called from focused_image_changed or
        # tck if called from geometry_change_callbacks... we ignore and fetch both as
        # needed.
        tck = self.center_spline._tck
        image = self.center_spline.rw.layer_stack.focused_image
        if tck is None or image is None:
            self.warped_view.image = None
        else:
            width = int(tck[0][-1] // 5)
            warped = resample.sample_image_along_spline(image, tck, width, order=order)
            self.warped_view.image = warped

    def _start_warp(self, pos):
        self._warp_start = pos.y()
        tck, points = self.center_spline._tck, self.center_spline._points
        self._warp_points = points
        px, py = interpolate.spline_interpolate(tck, num_points=len(points), derivative=1).T
        perps = numpy.transpose([py, -px])
        self._perps = perps / numpy.sqrt((perps**2).sum(axis=1))[:, numpy.newaxis]
        self._warp_positions = numpy.linspace(0, tck[0][-1], len(perps))
        self._warp_bandwidth = tck[0][-1] / self.center_spline.bandwidth # tck[0][-1] is approximate spline length

    def _warp_spline(self, pos, bandwidth_factor):
        bandwidth = self._warp_bandwidth * bandwidth_factor
        distances = self._warp_positions - pos.x()
        warp_coefficients = numpy.exp(-(distances/bandwidth)**2)
        displacement = pos.y() - self._warp_start
        displacements = displacement * self._perps * warp_coefficients[:, numpy.newaxis]
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self.center_spline._points = self._warp_points + displacements
        self.center_spline._generate_tck_from_points()

    def sceneEventFilter(self, watched, event):
        tck = self.center_spline._tck
        if tck is None:
            return False
        elif event.type() == Qt.QEvent.GraphicsSceneMousePress:
            self._start_warp(event.pos())
            return True
        elif event.type() == Qt.QEvent.GraphicsSceneMouseMove:
            bandwidth_factor = 1
            if event.modifiers() & Qt.Qt.ShiftModifier:
                bandwidth_factor = 2
            self._warp_spline(event.pos(), bandwidth_factor)
            return True
        elif event.type() == Qt.QEvent.GraphicsSceneMouseRelease:
            self._update_warped_view(None, order=1)
            return True
        return False