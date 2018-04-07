# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
import numpy

from zplib.curve import spline_geometry
from zplib.image import resample

from .. import shared_resources
from .. import internal_util
from .. import split_view
from . import base
from . import center_spline
from . import width_spline

class SplineOutline(base.RWGeometryItemMixin, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, color=Qt.Qt.green):
        center_pen = Qt.QPen(color)
        center_pen.setWidth(2)
        self.center_spline = center_spline.CenterSpline(ris_widget, pen=center_pen)
        if not hasattr(ris_widget, 'alt_view'):
            split_view.split_view_rw(ris_widget)
        width_pen = Qt.QPen(color)
        width_pen.setWidth(1)
        # need to construct width_spline second to make sure its scene event filter is added last
        self.width_spline = width_spline.WidthSpline(ris_widget.alt_view, pen=width_pen)
        self.warper = CenterSplineWarper(self.center_spline, self.width_spline, ris_widget.alt_view)
        outline_pen = Qt.QPen(color)
        outline_pen.setWidth(1)
        super().__init__(ris_widget, pen=outline_pen)
        self.center_spline.geometry_change_callbacks.append(self.update_outline)
        self.width_spline.geometry_change_callbacks.append(self.update_outline)

    def update_outline(self, _=None):
        # parameter _ gets called with width or centerline tck depending on which
        # callback triggers it...
        center_tck = self.center_spline.geometry
        width_tck = self.width_spline.geometry
        path = Qt.QPainterPath()
        if center_tck is not None and width_tck is not None:
            outline = spline_geometry.outline(center_tck, width_tck)[2]
            path.moveTo(*outline[0])
            for point in outline[1:]:
                path.lineTo(*point)
            path.closeSubpath()
        self.setPath(path)

class CenterSplineWarper(base.SceneListener):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, center_spline, width_spline, warped_view):
        super().__init__(warped_view)
        self.warped_view = warped_view
        self.warped_view.image_view.zoom_to_fit = False
        self._interpolate_order = 1
        self._ignore_mouse_moves = internal_util.Condition()
        self.center_spline = center_spline
        self.width_spline = width_spline
        center_spline.geometry_change_callbacks.append(self._update_warped_view)
        center_spline.rw.layer_stack.focused_image_changed.connect(self._update_warped_view)
        self._update_warped_view()

    def remove(self):
        super().remove()
        self.center_spline.rw.layer_stack.focused_image_changed.disconnect(self._update_warped_view)
        self.center_spline.geometry_change_callbacks.remove(self._update_warped_view)

    def _update_warped_view(self, _=None):
        # dummy parameter _ will either be image if called from focused_image_changed or
        # tck if called from geometry_change_callbacks... we ignore and fetch both as
        # needed.
        tck = self.center_spline._tck
        image = self.center_spline.rw.layer_stack.focused_image
        if tck is None or image is None:
            self.warped_view.image = None
        else:
            width = int(tck[0][-1] // 5)
            warped = resample.sample_image_along_spline(image.data, tck, width, order=self._interpolate_order)
            self.warped_view.image = warped

    def _start_warp(self, pos):
        self._warp_start = pos.y()
        self._warp_points = self.center_spline._points
        px, py = self.center_spline.evaluate_tck(derivative=1).T
        perps = numpy.transpose([py, -px])
        self._perps = perps / numpy.sqrt((perps**2).sum(axis=1))[:, numpy.newaxis]
        spline_len = self.center_spline._tck[0][-1] # tck[0][-1] is approximate spline length
        self._warp_positions = numpy.linspace(0, spline_len, len(perps))
        self._warp_bandwidth = spline_len / self.center_spline.BANDWIDTH

    def _warp_spline(self, pos):
        self._last_pos = pos
        bandwidth_factor = 0.5 if self.center_spline.fine_warp else 1
        bandwidth = self._warp_bandwidth * bandwidth_factor
        distances = self._warp_positions - pos.x()
        warp_coefficients = numpy.exp(-(distances/bandwidth)**2)
        displacement = pos.y() - self._warp_start
        displacements = displacement * self._perps * warp_coefficients[:, numpy.newaxis]
        disp_sqdist = (displacements**2).sum(axis=1)
        displacements[disp_sqdist < 4] = 0
        self.center_spline._points = self._warp_points + displacements
        with self._ignore_mouse_moves:
            self.center_spline._generate_tck_from_points()

    def sceneEventFilter(self, watched, event):
        tck = self.center_spline._tck
        if tck is None:
            return False
        elif (not self.width_spline.drawing and event.type() == Qt.QEvent.GraphicsSceneMousePress and
                event.modifiers() ^ Qt.Qt.AltModifier):
            if self.width_spline.isSelected():
                # deselect the width spline, because we swallow this mouse click which would otherwise
                # directly deselect it
                self.width_spline.setSelected(False)
            self._start_warp(event.pos())
            self._interpolate_order = 0
            return True
        elif (not self.width_spline.drawing and not self._ignore_mouse_moves and
                 event.type() == Qt.QEvent.GraphicsSceneMouseMove and event.modifiers() ^ Qt.Qt.AltModifier):
            # can get spurious mouse moves if image zoom changes while warping
            # (due to zoom-to-fit being enabled), which can then lead to
            # infinite recursion of zoom / warp / zoom / warp etc.
            # Break the chain by not warping if self.warping is set.
            self.center_spline.warping = True
            self._warp_spline(event.pos())
            return True
        elif self.center_spline.warping and event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Shift:
            self.center_spline.fine_warp = True
            self._warp_spline(self._last_pos)
            return True
        elif self.center_spline.warping and event.type() == Qt.QEvent.KeyRelease and event.key() == Qt.Qt.Key_Shift:
            self.center_spline.fine_warp = False
            self._warp_spline(self._last_pos)
            return True
        elif event.type() == Qt.QEvent.GraphicsSceneMouseRelease and self.center_spline.warping:
            self.center_spline.warping = False
            self.center_spline._geometry_changed()
            self._interpolate_order = 1
            self._update_warped_view()
            return True
        return False
