# This code is licensed under the MIT License (see LICENSE file for details)

import collections
from PyQt5 import Qt

from zplib.curve import spline_geometry

from . import annotator
from .. import split_view
from .. import shared_resources
from .. import internal_util
from ..overlay import base
from ..overlay import center_spline
from ..overlay import width_spline

class WormSplineAnnotation(annotator.AnnotationField):
    ENABLABLE = True

    def __init__(self, ris_widget, name='worm position', mean_width=None, width_pca_basis=None):
        self.ris_widget = ris_widget
        self.width_pca_basis = width_pca_basis
        super().__init__(name='worm position', default=mean_width)

    def init_widget(self):
        self.centerline = center_spline.CenterSpline(self.ris_widget)
        if not hasattr(self.ris_widget, 'alt_view'):
            split_view.split_view_rw(self.ris_widget)
        self.warper = center_spline.CenterSplineWarper(self.centerline, self.ris_widget.alt_view)
        self.widths = width_spline.WidthSpline(self.ris_widget.alt_view)

        self.centerline_reverser = ReverserListener(self.ris_widget, self.centerline, self.widths)
        self.widths_reverser = WidthsReverserListener(self.ris_widget.alt_view, self.centerline, self.widths)

        self.centerline.geometry_change_callbacks.append(self.on_centerline_change)
        self.widths.geometry_change_callbacks.append(self.on_widths_change)
        self._ignore_geometry_change = internal_util.Condition()

        self.outline = Qt.QGraphicsPathItem(self.ris_widget.image_scene.layer_stack_item)
        pen = Qt.QPen(Qt.Qt.green)
        pen.setWidth(1)
        pen.setCosmetic(True)
        self.outline.setPen(pen)

        self.widget = Qt.QGroupBox(self.name)
        layout = Qt.QGridLayout()
        self.widget.setLayout(layout)
        self.show_centerline = Qt.QCheckBox('show centerline')
        self.show_centerline.setChecked(True)
        self.show_centerline.toggled.connect(self.show_or_hide_centerline)
        layout.addWidget(self.show_centerline, 0, 0)
        self.show_outline = Qt.QCheckBox('show outline')
        self.show_outline.toggled.connect(self.update_outline)
        layout.addWidget(self.show_outline, 0, 1)

        self.undo_stack = collections.deque(maxlen=100)
        self.redo_stack = collections.deque(maxlen=100)

        # TODO: undo stack, revert to default widths, pca smooth widths, start-drawing button, straight-line centerline

    def on_centerline_change(self, center_tck):
        self.show_or_hide_centerline(self.show_centerline.isChecked())
        self.on_geometry_change(center_tck, self.widths.geometry)

    def on_widths_change(self, width_tck):
        self.on_geometry_change(self.centerline.geometry, width_tck)

    def on_geometry_change(self, center_tck, width_tck):
        self.update_outline()
        if not (self._ignore_geometry_change or self.centerline.warping or self.widths.warping):
            value = (center_tck, width_tck)
            self.undo_stack.append(value)
            self.redo_stack.clear()
            self.update_annotation_data(value)

    def undo(self):
        if len(self.undo_stack) > 0:
            self.redo_stack.append((self.centerline.geometry, self.widths.geometry))
            self.update_widget(self.undo_stack.pop())

    def redo(self):
        if len(self.redo_stack) > 0:
            self.undo_stack.append((self.centerline.geometry, self.widths.geometry))
            self.update_widget(self.redo_stack.pop())

    def update_widget(self, value):
        if value is None:
            value = None, None
        center_tck, width_tck = value
        with self._ignore_geometry_change:
            self.centerline.geometry = center_tck
            self.widths.geometry = width_tck

    def show_or_hide_centerline(self, show):
        # if show, then show the centerline.
        # if not, then only show if there is *no* centerline set: this way,
        # the line will be shown during manual drawing but hid once that line
        # is converted to a spline tck.
        self.centerline.setVisible(show or self.centerline.geometry is None)

    def update_outline(self, show=None):
        if show is None:
            show = self.show_outline.isChecked()
        if show:
            center_tck = self.centerline.geometry
            width_tck = self.widths.geometry
            if center_tck is None or width_tck is None:
                show = False
            else:
                outline = spline_geometry.outline(center_tck, width_tck)[2]
                path = Qt.QPainterPath()
                path.moveTo(*outline[0])
                for point in outline[1:]:
                    path.lineTo(*point)
                path.closeSubpath()
                self.outline.setPath(path)
        self.outline.setVisible(show)

class ReverserListener(base.SceneListener):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, centerline, widths):
        super().__init__(ris_widget.image_scene.layer_stack_item)
        self.centerline = centerline
        self.widths = widths

    def sceneEventFilter(self, watched, event):
        if event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_R:
            if self.centerline.geometry is not None:
                self.centerline.reverse_spline()
            if self.widths.geometry is not None:
                self.widths.reverse_spline()
            return True
        return False

class WidthsReverserListener(ReverserListener):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def sceneEventFilter(self, watched, event):
        # work around obscure interaction between CenterSplineWarper and WidthSpline,
        # where the former will steal a click that would otherwise deselect the latter
        if event.type() == Qt.QEvent.GraphicsSceneMousePress and self.widths.isSelected():
            self.widths.setSelected(False)
            return False
        return super().sceneEventFilter(watched, event)

