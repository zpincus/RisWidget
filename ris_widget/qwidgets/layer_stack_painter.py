# This code is licensed under the MIT License (see LICENSE file for details)

import numpy
from PyQt5 import Qt
from ..qgraphicsitems import layer_stack_painter_item
from .. import internal_util

class LabelEdit(Qt.QObject):
    value_changed = Qt.pyqtSignal(Qt.QObject)
    FLOAT_MAX = int(1e9)

    def __init__(self, layout, label_text):
        super().__init__()
        self.ignore_change = internal_util.Condition()
        self.label = Qt.QLabel(label_text)
        layout.addWidget(self.label)
        self.editbox = Qt.QLineEdit()
        self.editbox.editingFinished.connect(self._on_editbox_editing_finished)
        layout.addWidget(self.editbox)
        self.setEnabled(False)
        self._value = None

    def _on_editbox_editing_finished(self):
        if self.ignore_change:
            return
        try:
            v = self.parse_value(self.editbox.text())
            if v != self._value:
                self._value = v
                self.value_changed.emit(self)
        except ValueError:
            pass
        finally:
            self._update_editbox()

    @staticmethod
    def _val_to_str(value):
        return str(value)

    def _update_editbox(self):
        with self.ignore_change:
            self.editbox.setText(self._val_to_str(self._value))

    def parse_value(self, v):
        raise NotImplementedError()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        v = self.parse_value(v)
        if self._value != v:
            self._value = v
            self._update_editbox()
            self.value_changed.emit(self)

    def setEnabled(self, e):
        self.label.setEnabled(e)
        self.editbox.setEnabled(e)

class BrushSizeEdit(LabelEdit):
    def __init__(self, layout, label_text):
        super().__init__(layout, label_text)
        self.value = 5

    def parse_value(self, v):
        v = int(v)
        if v < 1:
            raise ValueError()
        if v %2 == 0:
            v += 1
        return v

class ImageValEdit(LabelEdit):
    NUMPY_DTYPE_TO_TYPE = {
        numpy.bool8  : bool,
        numpy.uint8  : int,
        numpy.uint16 : int,
        numpy.float32: float}

    def connect_image(self, image, max_default=True):
        if image is None:
            self.setEnabled(False)
            return
        self.setEnabled(True)
        type = self.NUMPY_DTYPE_TO_TYPE[image.data.dtype.type]
        min, max = image.valid_range
        nchannels = len(image.type)
        if self._value is not None:
            prev_type = self.type, self.min, self.max, self.nchannels
            if (type, min, max, nchannels) == prev_type:
                return
        self.type = type
        self.min = min
        self.max = max
        self.nchannels = nchannels
        default = max if max_default else min
        if nchannels == 1: # g
            self.value = default
        elif nchannels == 2: # ga
            self.value = default, max
        elif nchannels == 3: # rgb:
            self.value = default, default, default
        else: # rgba
            self.value = default, default, default, max

    def parse_value(self, v):
        if isinstance(v, str):
            v = v.split(',')
        try:
            v = iter(v)
        except TypeError:
            v = (v,)
        v = tuple(map(self.type, v))
        if any((vv < self.min or vv > self.max) for vv in v):
            raise ValueError()
        if len(v) not in (1, self.nchannels):
            raise ValueError()
        return v

    @staticmethod
    def _val_to_str(value):
        return ', '.join(map(str, value))
        if len(value) == 1:
            return str(value[0])

class LayerStackPainter(Qt.QWidget):
    def __init__(self, ris_widget, parent=None):
        self.painter_item = layer_stack_painter_item.LayerStackPainterItem(ris_widget.image_scene.layer_stack_item)
        super().__init__(parent)
        self.setWindowTitle('Layer Painter')
        widget_layout = Qt.QVBoxLayout()
        self.left_click_box = Qt.QCheckBox('Left click draws (alt-left pans)')
        widget_layout.addWidget(self.left_click_box)
        self.left_click_box.stateChanged.connect(self._on_left_click_changed)
        self.setLayout(widget_layout)
        self.brush_size = BrushSizeEdit(widget_layout, 'Brush size')
        self.brush_val = ImageValEdit(widget_layout, 'Right-click')
        self.alt_brush_val = ImageValEdit(widget_layout, 'Shift-right-click')
        widget_layout.addStretch()
        self.painter_item.target_image_changed.connect(self._on_target_image_changed)
        self.brush_size.value_changed.connect(self._on_brush_changed)
        self.brush_size.value_changed.connect(self._on_alt_brush_changed)
        self.brush_val.value_changed.connect(self._on_brush_changed)
        self.alt_brush_val.value_changed.connect(self._on_alt_brush_changed)
        self._on_target_image_changed()

    def showEvent(self, event):
        if not event.spontaneous(): # event is from Qt and widget became visible
            self.painter_item.show()

    def hideEvent(self, event):
        if not event.spontaneous(): # event is from Qt and widget became invisible
            # tell painter to deactivate
            self.painter_item.hide()

    def _on_left_click_changed(self, state):
        self.painter_item.left_click_draws = state
        if state:
            self.brush_val.label.setText('Left-click')
            self.alt_brush_val.label.setText('Shift-left-click')
        else:
            self.brush_val.label.setText('Right-click')
            self.alt_brush_val.label.setText('Shift-right-click')

    def _on_target_image_changed(self):
        self.brush_size.setEnabled(self.painter_item.target_image is not None)
        self.brush_val.connect_image(self.painter_item.target_image)
        self.alt_brush_val.connect_image(self.painter_item.target_image, max_default=False)

    def _on_brush_changed(self):
        self.painter_item.brush = self._get_brush(self.brush_val)

    def _on_alt_brush_changed(self):
        self.painter_item.alternate_brush = self._get_brush(self.alt_brush_val)

    def _get_brush(self, editor):
        ti = self.painter_item.target_image
        if ti is None:
            self.painter_item.brush = None
        else:
            size = self.brush_size.value
            mask = numpy.zeros((size, size), dtype=bool, order='F')
            r = int(size/2)
            x, y = numpy.indices(mask.shape) - r
            mask[y**2 + x**2 <= r**2] = True
            return layer_stack_painter_item.LayerStackPainterBrush(editor.value, mask, center=(r, r))