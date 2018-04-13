# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .overlay import centered_circle
from . import internal_util

class _MaskRegion(Qt.QObject):
    def __init__(self, rw):
        super().__init__()
        self.ellipse = Qt.QGraphicsEllipseItem(rw.image_scene.layer_stack_item)
        pen = Qt.QPen(Qt.Qt.green)
        pen.setWidth(3)
        pen.setStyle(Qt.Qt.DashLine)
        self.ellipse.setPen(pen)
        self.ellipse.hide()
        self._fade = Qt.QPropertyAnimation(self, b'opacity')
        self._fade.setDuration(3000) # 3 seconds
        self._fade.setKeyValueAt(0, 1)
        self._fade.setKeyValueAt(1, 0)
        self._fade.setEasingCurve(Qt.QEasingCurve.InOutCubic)
        self._fade.finished.connect(self.ellipse.hide)

    def fade(self):
        self.ellipse.show()
        self._fade.start()

    def _set_opacity(self, opacity):
        self.ellipse.setOpacity(opacity)

    opacity = Qt.pyqtProperty(float, fset=_set_opacity)


class HistogramMask:
    DEFAULT_MASKS = {None: None, 0.7: (0.5, 0.5, 0.4), 1: (0.5, 0.5, 0.55), 'custom': (0.5, 0.5, 0.25)}

    def __init__(self, rw, menu):
        self.masks = dict(self.DEFAULT_MASKS)
        self.layer_stack = rw.layer_stack
        self.mask_circle = centered_circle.CenteredCircle(rw)
        self.mask_circle.hide()
        self.ignore_geometry_changes = internal_util.Condition()
        self.mask_circle.geometry_change_callbacks.append(self.geometry_changed)

        self.display_mask = _MaskRegion(rw)

        hist_mask = menu.addMenu('Histogram Mask')
        mask_actions = Qt.QActionGroup(menu)
        no_mask = Qt.QAction('No Mask', mask_actions)
        no_mask.setCheckable(True)
        no_mask.toggled.connect(lambda checked: self.mask_toggled(checked, None))

        mask_07 = Qt.QAction('0.7\N{MULTIPLICATION SIGN} Coupler', mask_actions)
        mask_07.setCheckable(True)
        mask_07.toggled.connect(lambda checked: self.mask_toggled(checked, 0.7))

        mask_1 = Qt.QAction('1\N{MULTIPLICATION SIGN} Coupler', mask_actions)
        mask_1.setCheckable(True)
        mask_1.toggled.connect(lambda checked: self.mask_toggled(checked, 1))

        self.custom_mask = Qt.QAction('Custom Mask', mask_actions)
        self.custom_mask.setCheckable(True)
        self.custom_mask.toggled.connect(lambda checked: self.mask_toggled(checked, 'custom'))

        hist_mask.addActions(mask_actions.actions())
        hist_mask.addSeparator()
        self.show_action = Qt.QAction('Show Mask')
        hist_mask.addAction(self.show_action)
        self.show_action.setCheckable(True)
        self.show_action.setChecked(False)
        self.show_action.toggled.connect(self.mask_circle.setVisible)

        no_mask.setChecked(True)

    def mask_toggled(self, checked, mask_name):
        if not checked:
            return # ignore the turning-off actions
        mask = self.masks[mask_name]
        self.layer_stack.histogram_mask = mask
        with self.ignore_geometry_changes:
            image = self.layer_stack.layers[0].image
            if mask is None or image is None:
                geometry = None
            else:
                shape = image.data.shape
                cx, cy, r = mask
                cx *= shape[0]
                cy *= shape[1]
                r *= shape[0]
                geometry = cx, cy, r
            self.mask_circle.geometry = geometry
        if mask_name == 'custom':
            self.show_action.setChecked(True)
        elif mask_name is None:
            self.show_action.setChecked(False)
        elif not self.show_action.isChecked():
            self.display_mask.ellipse.setRect(self.mask_circle.rect())
            self.display_mask.fade()

    def geometry_changed(self, geometry):
        if not self.ignore_geometry_changes:
            image = self.layer_stack.layers[0].image
            if image is None:
                return
            shape = image.data.shape
            cx, cy, r = geometry
            cx /= shape[0]
            cy /= shape[1]
            r /= shape[0]
            self.layer_stack.histogram_mask = self.masks['custom'] = (cx, cy, r)
            self.custom_mask.setChecked(True)