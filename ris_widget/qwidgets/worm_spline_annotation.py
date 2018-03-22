# This code is licensed under the MIT License (see LICENSE file for details)

import collections
from PyQt5 import Qt
import numpy

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

    def __init__(self, ris_widget, name='worm position', mean_widths=None, width_pca_basis=None):
        self.ris_widget = ris_widget
        if width_pca_basis is not None:
            if not numpy.allclose((width_pca_basis**2).sum(axis=1), numpy.ones(len(width_pca_basis))):
                raise ValueError('a unit-length (non-normalized) PCA basis must be provided')
        self.width_pca_basis = width_pca_basis
        self.mean_widths = mean_widths
        super().__init__(name)

    def init_widget(self):
        self.centerline = center_spline.CenterSpline(self.ris_widget)
        if not hasattr(self.ris_widget, 'alt_view'):
            split_view.split_view_rw(self.ris_widget)
        self.warper = center_spline.CenterSplineWarper(self.centerline, self.ris_widget.alt_view)
        self.widths = width_spline.WidthSpline(self.ris_widget.alt_view)

        if self.mean_widths is None:
            self.default_widths = None
        else:
            x = numpy.linspace(0, 1, len(self.mean_widths))
            self.default_widths = self.widths.calculate_tck(x, self.mean_widths)
        self.default = (None, self.default_widths)

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

        self.hidden_pen = Qt.QPen(Qt.Qt.transparent)

        self.widget = Qt.QGroupBox(self.name)
        self._current_row = 0

        layout = Qt.QGridLayout()
        self.widget.setLayout(layout)
        self.show_centerline = Qt.QCheckBox('Show Center')
        self.show_centerline.setChecked(True)
        self.show_centerline.toggled.connect(self.show_or_hide_centerline)
        self.show_outline = Qt.QCheckBox('Show Outline')
        self.show_outline.setChecked(True)
        self.show_outline.toggled.connect(self.update_outline)
        self._add_row(layout, self.show_centerline, self.show_outline)

        self.undo_stack = collections.deque(maxlen=100)
        self.redo_stack = collections.deque(maxlen=100)
        self.undo_button = Qt.QPushButton('Undo')
        self.undo_button.clicked.connect(self.undo)
        Qt.QShortcut(Qt.QKeySequence.Undo, self.widget, self.undo_button.click)
        self.redo_button = Qt.QPushButton('Redo')
        self.redo_button.clicked.connect(self.redo)
        Qt.QShortcut(Qt.QKeySequence.Redo, self.widget, self.redo_button.click)
        self._add_row(layout, self.undo_button, self.redo_button)


        self.draw_center_button = Qt.QPushButton('Draw Center')
        self.draw_center_button.setCheckable(True)
        self.draw_center_button.clicked.connect(self.draw_centerline)
        self.draw_width_button = Qt.QPushButton('Draw Widths')
        self.draw_width_button.setCheckable(True)
        self.draw_width_button.clicked.connect(self.draw_widths)
        self._add_row(layout, self.draw_center_button, self.draw_width_button)

        self.smooth_center_button = Qt.QPushButton('Smooth Center')
        self.smooth_center_button.clicked.connect(self.centerline.smooth)
        self.smooth_width_button = Qt.QPushButton('Smooth Widths')
        self.smooth_width_button.clicked.connect(self.widths.smooth)
        self._add_row(layout, self.smooth_center_button, self.smooth_width_button)

        self.default_button = Qt.QPushButton('Default Widths')
        self.default_button.clicked.connect(self.set_default_widths)
        self.pca_button = Qt.QPushButton('PCA(Widths)')
        self.pca_button.clicked.connect(self.pca_smooth_widths)
        self._add_row(layout, self.default_button, self.pca_button)

        self.fine_mode = Qt.QCheckBox('Fine Warping')
        self.fine_mode.setChecked(False)
        self.fine_mode.toggled.connect(self.toggle_fine_mode)
        self._add_row(layout, self.fine_mode)

    def _add_row(self, layout, *widgets):
        if len(widgets) == 1:
            layout.addWidget(widgets[0], self._current_row, 0, 1, -1, Qt.Qt.AlignCenter)
        else:
            for i, widget in enumerate(widgets):
                layout.addWidget(widget, self._current_row, i)
        self._current_row += 1

    def on_centerline_change(self, center_tck):
        self.show_or_hide_centerline(self.show_centerline.isChecked())
        self.on_geometry_change(center_tck, self.widths.geometry)

    def on_widths_change(self, width_tck):
        self.on_geometry_change(self.centerline.geometry, width_tck)

    def on_geometry_change(self, center_tck, width_tck):
        self.update_outline()
        if not (self._ignore_geometry_change or self.centerline.warping or self.widths.warping):
            value = (center_tck, width_tck)
            self.undo_stack.append(self.annotations[self.name]) # put current value on the undo stack
            self.redo_stack.clear()
            self._enable_buttons(center_tck, width_tck)
            self.update_annotation_data(value)

    def undo(self):
        if len(self.undo_stack) > 0:
            self.redo_stack.append((self.centerline.geometry, self.widths.geometry))
            new_state = self.undo_stack.pop()
            self._update_widget(*new_state)
            self._enable_buttons(*new_state)

    def redo(self):
        if len(self.redo_stack) > 0:
            self.undo_stack.append((self.centerline.geometry, self.widths.geometry))
            new_state = self.redo_stack.pop()
            self._update_widget(*new_state)
            self._enable_buttons(*new_state)

    def _enable_buttons(self, center_tck, width_tck):
        self.undo_button.setEnabled(len(self.undo_stack) > 0)
        self.redo_button.setEnabled(len(self.redo_stack) > 0)
        self.smooth_center_button.setEnabled(center_tck is not None)
        self.smooth_width_button.setEnabled(center_tck is not None and width_tck is not None)
        self.draw_center_button.setChecked(self.centerline.drawing)
        self.draw_width_button.setEnabled(center_tck is not None)
        self.draw_width_button.setChecked(self.widths.drawing)
        self.default_button.setEnabled(self.default_widths is not None and center_tck is not None)
        self.pca_button.setEnabled(self.width_pca_basis is not None and center_tck is not None and width_tck is not None)

    def set_default_widths(self):
        if self.default_widths is not None:
            self.widths.geometry = self.default_widths

    def pca_smooth_widths(self):
        if self.mean_widths is not None and self.width_pca_basis is not None:
            x = numpy.linspace(0, 1, len(self.mean_widths))
            widths = self.widths.evaluate_tck(x)
            pca_projection = numpy.dot(widths - self.mean_widths, self.width_pca_basis.T)
            pca_reconstruction = self.mean_widths + numpy.dot(pca_projection, self.width_pca_basis)
            self.widths.geometry = self.widths.calculate_tck(x, pca_reconstruction)

    def draw_centerline(self, draw):
        with self._ignore_geometry_change:
            self.centerline.geometry = None
        if draw:
            self.centerline.start_drawing()

    def draw_widths(self, draw):
        with self._ignore_geometry_change:
            self.widths.geometry = None
        if draw:
            self.widths.start_drawing()

    def update_widget(self, value):
        # called only when switching pages
        if value is None:
            value = None, None
        center_tck, width_tck = value
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.ris_widget.alt_view.image_view.zoom = self.ris_widget.image_view.zoom
        self._update_widget(center_tck, width_tck)

    def _update_widget(self, center_tck, width_tck):
        self._enable_buttons(center_tck, width_tck)
        with self._ignore_geometry_change:
            self.centerline.geometry = center_tck
            self.widths.geometry = width_tck

    def show_or_hide_centerline(self, show):
        # if show, then show the centerline.
        # if not, then only show if there is *no* centerline set: this way,
        # the line will be shown during manual drawing but hid once that line
        # is converted to a spline tck.
        if show or self.centerline.geometry is None:
            self.centerline.setPen(self.centerline.display_pen)
        else:
            self.centerline.setPen(self.hidden_pen)

    def toggle_fine_mode(self, v):
        self.centerline.fine_warp = v
        self.widths.fine_warp = v

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

