# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
import numpy

from zplib.curve import interpolate
from zplib.image import resample

from .. import shared_resources
from . import center_spline

class WidthSpline(center_spline.CenterSpline, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    SMOOTH_BASE = 32

    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None):
        self._tck_x = numpy.linspace(0, 1, self.SPLINE_POINTS)
        super().__init__(ris_widget, color, geometry)
        self.bandwidth = 15
        self.display_pen.setWidth(1)
        self.layer = None
        self.parentItem().bounding_rect_changed.connect(self._update_image_shape)
        self._update_image_shape()

    def _update_image_shape(self):
        # bounding rect change means that the image at layers[0] has changed in some way
        self.image_shape = None
        layers = self.rw.layer_stack.layers
        if len(layers) > 0 and layers[0].image is not None:
            self.image_shape = layers[0].image.data.shape
        self._update_path()

    def remove(self):
        super().remove()
        self.parentItem().bounding_rect_changed.disconnect(self._update_image_shape)

    def _update_path(self):
        self.path = Qt.QPainterPath()
        tck = self._tck
        if tck is not None and self.image_shape is not None:
            width, height = self.image_shape
            centerline_y = height / 2
            self.path.moveTo(0, centerline_y)
            image_x = self._tck_x * (width - 1)
            points = interpolate.spline_evaluate(tck, self._tck_x)
            for x, y in zip(image_x, centerline_y - points):
                self.path.lineTo(x, y)
            for x, y in zip(image_x[::-1], centerline_y + points[::-1]):
                self.path.lineTo(x, y)
            self.path.closeSubpath()
        self.setPath(self.path)

    def _update_points(self):
        tck = self._tck
        if tck is not None:
            self._points = numpy.maximum(interpolate.spline_evaluate(tck, self._tck_x), 0.1)
        else:
            self._points = numpy.empty_like(self._tck_x)
            self._points.fill(numpy.nan)

    def _generate_tck_from_points(self):
        x = self._tck_x
        widths = numpy.asarray(self._points)
        if self._drawing:
            # un-filled widths may be nan
            good_widths = numpy.isfinite(widths)
            x = x[good_widths]
            widths = widths[good_widths]
        l = len(widths)
        if l > 4:
            tck = interpolate.fit_nonparametric_spline(x, widths, smoothing=self._smoothing * l)
        else:
            tck = None
        self._set_tck(tck)
        if self._drawing:
            # now make a new _points that doesn't have nans in it
            self._update_points()

    def _add_point(self, pos):
        if self.image_shape is None:
            return
        width, height = self.image_shape
        centerline_y = height / 2
        x, y = pos.x(), pos.y()
        if self._last_pos is not None:
            last_x, y_sign = self._last_pos
            if abs(x - last_x) < 6:
                return
        else:
            # invert widths if we started out past the centerline
            y_sign = 1 if y < centerline_y else -1
        if not 0 <= x <= width:
            return
        x_i = round((len(self._points) - 1) * x / width)
        self._points[x_i] = max(y_sign * (centerline_y - y), 0.1)
        self._last_pos = (x, y_sign)
        # now draw points
        good_points = numpy.isfinite(self._points)
        xs = self._tck_x[good_points] * width
        ys = self._points[good_points]
        self.path = Qt.QPainterPath()
        self.path.moveTo(xs[0], centerline_y - ys[0])
        for x, y in zip(xs[1:], centerline_y - ys[1:]):
            self.path.lineTo(x, y)
        self.path.moveTo(xs[0], centerline_y + ys[0])
        for x, y in zip(xs[1:], centerline_y + ys[1:]):
            self.path.lineTo(x, y)
        self.setPath(self.path)

    def _start_warp(self, pos):
        self._warp_start = pos.y()
        self._warp_points = self._points

    def _warp_spline(self, pos, bandwidth_factor):
        self._last_pos = pos
        if self.image_shape is None:
            return
        width, height = self.image_shape
        centerline_y = height / 2
        bandwidth = bandwidth_factor / self.bandwidth
        distances = self._tck_x - pos.x() / width
        warp_coefficients = numpy.exp(-(distances/bandwidth)**2)
        displacement = self._warp_start - pos.y()
        if self._warp_start > centerline_y:
            displacement *= -1
        displacements = displacement * warp_coefficients
        displacements[displacements**2 < 4] = 0
        self._points = numpy.maximum(self._warp_points + displacements, 0.1)
        self._generate_tck_from_points()

    def _extend_endpoint(self, pos):
        # no endpoint-extending for width splines...
        pass
