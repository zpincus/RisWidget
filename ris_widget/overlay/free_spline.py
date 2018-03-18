# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
import numpy

from zplib.curve import interpolate
from zplib.image import resample

from .. import shared_resources
from . import base

class FreeSpline(base.RWGeometryItemMixin, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None):
        self.drawing = False
        self._smoothing = 5
        self._tck = None
        self.bandwidth = 20
        self.warped_view = getattr(ris_widget, 'alt_view', None)
        if self.warped_view is not None:
            ris_widget.layer_stack.focused_image_changed.connect(self._on_focused_image_changed)
            self._on_focused_image_changed(ris_widget.layer_stack.focused_image)
            self._drag_detector = WarpedViewDragDetector(self, self.warped_view)
        super().__init__(ris_widget, color, geometry)
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable)

    def remove(self):
        super().remove()
        if self.warped_view is not None:
            self.rw.layer_stack.focused_image_changed.disconnect(self._on_focused_image_changed)
            self._drag_detector.remove()

    @property
    def geometry(self):
        return self._tck

    @geometry.setter
    def geometry(self, tck):
        self.setSelected(False)
        self.set_tck(tck)

    def set_tck(self, tck, points=None):
        self.drawing = False
        self._tck = tck
        self.path = Qt.QPainterPath()
        if self.warped_view is not None:
            self._update_warped_view()
        if tck is not None:
            if points is None:
                self._generate_points_from_tck()
            else:
                self.points = points
            bezier_elements = interpolate.spline_to_bezier(tck)
            self.path.moveTo(*bezier_elements[0][0])
            for (sx, sy), (c1x, c1y), (c2x, c2y), (ex, ey) in bezier_elements:
                self.path.cubicTo(c1x, c1y, c2x, c2y, ex, ey)
        self.setPath(self.path)
        self._geometry_changed()

    @property
    def smoothing(self):
        return self._smoothing

    @smoothing.setter
    def smoothing(self, value):
        self._smoothing = value
        if self._tck is not None:
            self._generate_tck_from_points()

    def _update_warped_view(self):
        if self._tck is None:
            self.warped_view.image = None
        elif self._image is not None:
            width = self._tck[0][-1] / 5
            warped = resample.sample_image_along_spline(self._image, self._tck, width, order=1)
            self.warped_view.image = warped

    def _on_focused_image_changed(self, image):
        self._image = None if image is None else image.data
        if self._tck is not None:
            self._update_warped_view()

    def _generate_tck_from_points(self):
        self.points = numpy.array(self.points)
        l = len(self.points)
        if l > 1:
            tck = interpolate.fit_spline(self.points, smoothing=self._smoothing * l)
            self.set_tck(tck, self.points)

    def _generate_points_from_tck(self):
        assert self._tck is not None
        self.points = interpolate.spline_interpolate(self._tck, num_points=300)

    def _start_drawing(self):
        self.drawing = True
        self.display_pen.setStyle(Qt.Qt.DotLine)
        self.setPen(self.display_pen)
        self.points = []
        self._last_pos = None
        self.path = Qt.QPainterPath()
        self.setPath(self.path)

    def _stop_drawing(self):
        self.drawing = False
        self.display_pen.setStyle(Qt.Qt.SolidLine)
        self.setPen(self.display_pen)
        if len(self.points) > 4:
            self._generate_tck_from_points()
        else:
            self.set_tck(None)

    def _add_point(self, pos):
        self.points.append((pos.x(), pos.y()))
        if self._last_pos is None:
            self.path.moveTo(pos)
        else:
            self.path.lineTo(pos)
        self._last_pos = pos
        self.setPath(self.path)

    def _start_warp(self, x, y):
        self._warp_start = numpy.array([x, y])
        self._generate_points_from_tck()
        self._warp_points = self.points
        self._warp_distances = numpy.sqrt(((self._warp_start - self.points)**2).sum(axis=1))
        self._warp_bandwidth = self._tck[0][-1] / self.bandwidth # tck[0][-1] is approximate spline length

    def _warp_spline(self, x, y, bandwidth_factor):
        end = numpy.array([x, y])
        delta = end - self._warp_start
        bandwidth = self._warp_bandwidth * bandwidth_factor
        warp_coefficients = numpy.exp(-(self._warp_distances/bandwidth)**2)
        displacements = numpy.outer(warp_coefficients, delta)
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self.points = self._warp_points + displacements
        self._generate_tck_from_points()

    def _start_perpendicular_warp(self, x, y):
        self._perp_warp_start = y
        self._generate_points_from_tck()
        self._warp_points = self.points
        px, py = interpolate.spline_interpolate(self._tck, num_points=len(self.points), derivative=1).T
        perps = numpy.transpose([py, -px])
        self._perps = perps / numpy.sqrt((perps**2).sum(axis=1))[:, numpy.newaxis]
        self._perp_warp_positions = numpy.linspace(0, self._tck[0][-1], len(perps))
        self._perp_warp_bandwidth = self._tck[0][-1] / self.bandwidth # tck[0][-1] is approximate spline length

    def _warp_spline_perpendicular(self, x, y, bandwidth_factor):
        displacement = y - self._perp_warp_start
        bandwidth = self._perp_warp_bandwidth * bandwidth_factor
        distances = self._perp_warp_positions - x
        warp_coefficients = numpy.exp(-(distances/bandwidth)**2)
        displacements = displacement * self._perps * warp_coefficients[:, numpy.newaxis]
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self.points = self._warp_points + displacements
        self._generate_tck_from_points()

    def _extend_endpoint(self, x, y):
        new_end = numpy.array([x, y])
        old_ends = self.points[[0,-1]]
        dists = ((old_ends - new_end)**2).sum(axis=1)
        if dists[0] < dists[1]:
            cat_list = [[new_end], self.points]
        else:
            cat_list = [self.points, [new_end]]
        self.points = numpy.concatenate(cat_list, axis=0)
        self._generate_tck_from_points()
        self._generate_points_from_tck()

    def _reverse_spline(self):
        t, c, k = self._tck
        self.set_tck(interpolate.reverse_spline(tck), self.points[::-1])

    def sceneEventFilter(self, watched, event):
        if self.drawing and event.type() in {Qt.QEvent.GraphicsSceneMousePress, Qt.QEvent.GraphicsSceneMouseMove}:
            pos = event.pos()
            if self._last_pos is None or (pos.x() - self._last_pos.x())**2 + (pos.y() - self._last_pos.y())**2 > 36:
                self._add_point(pos)
            return True
        elif self.drawing and event.type() == Qt.QEvent.GraphicsSceneMouseRelease:
            self._stop_drawing()
            return True
        elif self._tck is not None and event.type() == Qt.QEvent.GraphicsSceneMousePress and event.modifiers() & Qt.Qt.ShiftModifier:
            pos = event.pos()
            self._extend_endpoint(pos.x(), pos.y())
            return True
        elif self._tck is None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Shift:
            if not self.drawing:
                self._start_drawing()
            else:
                self._stop_drawing()
            return True
        elif self.shared_filter(event):
            return True
        return super().sceneEventFilter(watched, event)

    def shared_filter(self, event):
        if event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_S:
            if event.modifiers() & Qt.Qt.ShiftModifier:
                self.smoothing = min(self.smoothing * 2, 160) # 5 * 2**5
            else:
                self.smoothing = max(self.smoothing / 2, 0.625) # 5 / 2**2
            return True
        elif self._tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_R:
            self._reverse_spline()
            return True
        elif self._tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_D and event.modifiers() & Qt.Qt.ShiftModifier:
            self.geometry = None
            return True
        return False

    def mousePressEvent(self, event):
        p = event.pos()
        self._start_warp(p.x(), p.y())

    def mouseMoveEvent(self, event):
        bandwidth_factor = 1
        if event.modifiers() & Qt.Qt.ShiftModifier:
            bandwidth_factor = 2
        p = event.pos()
        self._warp_spline(p.x(), p.y(), bandwidth_factor)


class WarpedViewDragDetector(Qt.QGraphicsObject):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, free_spline, warped_view):
        self.free_spline = free_spline
        layer_stack_item = warped_view.image_scene.layer_stack_item
        super().__init__(layer_stack_item)
        self.setFlag(Qt.QGraphicsItem.ItemHasNoContents)
        layer_stack_item.installSceneEventFilter(self)

    def boundingRect(self):
        return Qt.QRectF()

    def remove(self):
        self.parentItem().removeSceneEventFilter(self)

    def sceneEventFilter(self, watched, event):
        if self.free_spline._tck is not None and event.type() == Qt.QEvent.GraphicsSceneMousePress:
            p = event.pos()
            self.free_spline._start_perpendicular_warp(p.x(), p.y())
            return True
        elif self.free_spline._tck is not None and event.type() == Qt.QEvent.GraphicsSceneMouseMove:
            bandwidth_factor = 1
            if event.modifiers() & Qt.Qt.ShiftModifier:
                bandwidth_factor = 2
            p = event.pos()
            self.free_spline._warp_spline_perpendicular(p.x(), p.y(), bandwidth_factor)
            return True
        elif self.free_spline.shared_filter(event):
            return True
        return False