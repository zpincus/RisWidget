# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
import numpy

from zplib.curve import interpolate
from zplib.image import resample

from .. import shared_resources
from . import center_spline

class WidthSpline(center_spline.CenterSpline, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None):
        super().__init__(ris_widget, color, geometry)
        self.display_pen.setWidth(1)
        self._tck_x = numpy.linspace(0, 1, 300)
        ris_widget.layer_stack.focused_image_changed.connect(self._update_path)
        self._update_path()

    def remove(self):
        super().remove()
        self.rw.layer_stack.focused_image_changed.disconnect(self._update_path)

    def _set_tck(self, tck):
        self.drawing = False
        self._tck = tck
        self._update_path()
        self._geometry_changed()

    def _update_path(self):
        self.path = Qt.QPainterPath()
        tck = self._tck
        image = self.rw.layer_stack.focused_image
        self.image_shape = None if image is None else image.data.shape
        if tck is not None and self.image_shape is not None:
            width, height = self.image_shape
            centerline_y = height / 2
            self._points = interpolate.spline_evaluate(tck, self._tck_x)
            self.path.moveTo(0, centerline_y)
            image_x = self._tck_x * (width - 1)
            for x, y in zip(image_x, centerline_y - self._points):
                self.path.lineTo(x, y)
            for x, y in zip(image_x, centerline_y + self._points[::-1]):
                self.path.lineTo(x, y)
            self.path.closePath()
        self.setPath(self.path)

    def _generate_tck_from_points(self, points):
        widths = numpy.asarray(points)
        if self.drawing:
            # widths may contain nan
        else:
            x = self._tck_x
        l = len(y)
        if l > 1:
            tck = interpolate.fit_nonparametric_spline(x, widths, smoothing=self._smoothing * l)
        else:
            tck = None
        self._set_tck(tck)

    def _start_drawing(self):
        super()._start_drawing()
        self._points = numpy.empty_like(self._tck_x)
        self._points.fill(numpy.nan)

    def _add_point(self, pos):
        if self.image_shape is None:
            return
        width, height = self.image_shape
        centerline_y = height / 2
        x, y = pos.x(), pos.y()
        if self._last_pos is not None:
            last_x, last_y = self._last_pos
            if abs(x - last_x) < 6:
                return
            if last_y < centerline_y and y >= centerline_y:
                y = centerline_y - 1
            elif last_y > centerline_y and y <= centerline_y:
                y = centerline_y + 1
        x_i = int(round(len(self._tck_x) * x / (width - 1)))
        self._points.append((x, y))
        self._last_pos = (x, y)

    def _start_warp(self, pos):
        self._warp_start = numpy.array([pos.x(), pos.y()])
        self._warp_points = self._points
        self._warp_distances = numpy.sqrt(((self._warp_start - self._points)**2).sum(axis=1))
        self._warp_bandwidth = self._tck[0][-1] / self.bandwidth # tck[0][-1] is approximate spline length

    def _warp_spline(self, pos, bandwidth_factor):
        end = numpy.array([pos.x(), pos.y()])
        delta = end - self._warp_start
        bandwidth = self._warp_bandwidth * bandwidth_factor
        warp_coefficients = numpy.exp(-(self._warp_distances/bandwidth)**2)
        displacements = numpy.outer(warp_coefficients, delta)
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self._generate_tck_from_points(self._warp_points + displacements)

    def _extend_endpoint(self, pos):
        new_end = numpy.array([pos.x(), pos.y()])
        old_ends = self._points[[0,-1]]
        dists = ((old_ends - new_end)**2).sum(axis=1)
        if dists[0] < dists[1]:
            new_points = [[new_end], self._points]
        else:
            new_points = [self._points, [new_end]]
        self._generate_tck_from_points(numpy.concatenate(new_points))

    def _reverse_spline(self):
        self._set_tck(interpolate.reverse_spline(self._tck))

    def sceneEventFilter(self, watched, event):
        tck, drawing = self._tck, self.drawing
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
        elif tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}:
            self.geometry = None
            return True
        elif tck is not None and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_R:
            self._reverse_spline()
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
        center_spline.rw.layer_stack.focused_image_changed.connect(self._on_focused_image_changed)
        self._on_focused_image_changed(center_spline.rw.layer_stack.focused_image)

    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    def type(self):
        return self.QGRAPHICSITEM_TYPE

    def boundingRect(self):
        return Qt.QRectF()

    def remove(self):
        self.parentItem().removeSceneEventFilter(self)
        self.center_spline.rw.layer_stack.focused_image_changed.disconnect(self._on_focused_image_changed)

    def _on_focused_image_changed(self, image):
        self._image = None if image is None else image.data
        self._update_warped_view()

    def _update_warped_view(self):
        tck = self.center_spline._tck
        if tck is None or self._image is None:
            self.warped_view.image = None
        else:
            width = tck[0][-1] / 5
            warped = resample.sample_image_along_spline(self._image, tck, width, order=1)
            self.warped_view.image = warped

    def _start_warp(self, pos):
        self._perp_warp_start = pos.y()
        tck, points = self.center_spline._tck, self.center_spline._points
        self._warp_points = self.center_spline._points
        px, py = interpolate.spline_interpolate(tck, num_points=len(points), derivative=1).T
        perps = numpy.transpose([py, -px])
        self._perps = perps / numpy.sqrt((perps**2).sum(axis=1))[:, numpy.newaxis]
        self._warp_positions = numpy.linspace(0, tck[0][-1], len(perps))
        self._warp_bandwidth = tck[0][-1] / self.center_spline.bandwidth # tck[0][-1] is approximate spline length

    def _warp_spline(self, pos, bandwidth_factor):
        displacement = pos.y() - self._perp_warp_start
        bandwidth = self._warp_bandwidth * bandwidth_factor
        distances = self._warp_positions - pos.x()
        warp_coefficients = numpy.exp(-(distances/bandwidth)**2)
        displacements = displacement * self._perps * warp_coefficients[:, numpy.newaxis]
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self.center_spline._generate_tck_from_points(self._warp_points + displacements)

    def sceneEventFilter(self, watched, event):
        tck = self.center_spline._tck
        if tck is not None and event.type() == Qt.QEvent.GraphicsSceneMousePress:
            self._start_warp(event.pos())
            return True
        elif tck is not None and event.type() == Qt.QEvent.GraphicsSceneMouseMove:
            bandwidth_factor = 1
            if event.modifiers() & Qt.Qt.ShiftModifier:
                bandwidth_factor = 2
            self._warp_spline(event.pos(), bandwidth_factor)
            return True
        return False