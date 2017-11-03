# The MIT License (MIT)
#
# Copyright (c) 2015 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Erik Hvatum <ice.rikh@gmail.com>

import json
from PyQt5 import Qt
import numpy
from .object_model import uniform_signaling_list
from . import image
from . import layer

class LayerList(uniform_signaling_list.UniformSignalingList):
    @classmethod
    def from_json(cls, json_str):
        prop_stack = json.loads(json_str)['layer property stack']
        layers = cls()
        for props in prop_stack:
            layers.append(layer.Layer.from_savable_properties_dict(props))
        return layers

    def to_json(self):
        return json.dumps(
            {
                'layer property stack' :
                [
                    layer.get_savable_properties_dict() for layer in self
                ]
            },
            ensure_ascii=False, indent=1
        )

    def take_input_element(self, obj):
        if isinstance(obj, (numpy.ndarray, image.Image)):
            obj = layer.Layer(obj)
        elif isinstance(obj, layer.Layer):
            if hasattr(self, '_list') and obj in self._list:
                raise ValueError('A given layer can only be in the layer stack once.')
        else:
            raise TypeError("All inputs must be numpy.ndarray, Image, or Layer")
        return obj

class LayerStack(Qt.QObject):
    """LayerStack: The owner of a LayerList (L.layers, in ascending order, with bottom layer - ie, backmost - as element 0) and selection model that is
    referenced by various other objects such as LayerStackItem, LayerTable, RisWidget, and Flipbooks.

    Signals:
    * layer_focus_changed(layer_stack, old_focused_layer, focused_layer): layer_stack.focused_layer changed from old_focused layer to focused_layer,
    its current value."""
    layer_focus_changed = Qt.pyqtSignal(Qt.QObject, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._layers = LayerList()
        self._layers.inserting.connect(self._on_inserting_into_layers)
        self._layers.removing.connect(self._on_removing_from_layers)
        self._layers.replacing.connect(self._on_replacing_in_layers)
        self._layers.replaced.connect(self._on_replaced_in_layers)
        # Must be QueuedConnection in order to avoid race condition where self._on_inserting_into_layers may be called before any associated model's
        # "inserting" handler, which would cause ensure_layer_focused, if layers was empty before insertion, to attempt to focus row 0 before associated
        # models are even aware that a row has been inserting.
        self._layers.inserted.connect(self._delayed_on_inserted_into_layers, Qt.Qt.QueuedConnection)
        self._layers.removed.connect(self._delayed_on_removed_from_layers, Qt.Qt.QueuedConnection)

        self._mask_radius = None
        self._selection_model = None
        self.auto_min_max_all_action = Qt.QAction(self)
        self.auto_min_max_all_action.setText('Auto Min/Max')
        self.auto_min_max_all_action.setCheckable(True)
        self.auto_min_max_all_action.setChecked(True)
        # From the Qt docs: The triggered signal is emitted when an action is activated by the user; for example, when the user clicks a menu option,
        # toolbar button, or presses an action's shortcut key combination, or when trigger() was called. Notably, it is not emitted when setChecked()
        # or toggle() is called.
        self.auto_min_max_all_action.triggered.connect(self._on_master_enable_auto_min_max_triggered)
        # From the Qt docs: The toggled signal is emitted whenever a checkable action changes its isChecked() status. This can be the result of a user
        # interaction, or because setChecked() was called.
        self.auto_min_max_all_action.toggled.connect(self._on_master_enable_auto_min_max_toggled)
        self.solo_layer_mode_action = Qt.QAction(self)
        self.solo_layer_mode_action.setText('Solo Current Layer')
        self.solo_layer_mode_action.setCheckable(True)
        self.solo_layer_mode_action.setChecked(False)
        self.solo_layer_mode_action.setToolTip('Show only the currently selected layer')

    @property
    def layers(self):
        return self._layers

    def set_selection_model(self, v):
        assert isinstance(v, Qt.QItemSelectionModel)
        if self._selection_model is not None:
            raise RuntimeError('only set selection model once, immediately after construction')
        v.currentRowChanged.connect(self._on_current_row_changed)
        self._selection_model = v

    @property
    def focused_layer_idx(self):
        sm = self._selection_model
        m = sm.model()
        midx = sm.currentIndex()
        if isinstance(m, Qt.QAbstractProxyModel):
            # Selection model is with reference to table view's model, which is a proxy model (probably an InvertingProxyModel)
            if not midx.isValid():
                return
            midx = m.mapToSource(midx)
        if midx.isValid():
            return midx.row()

    @property
    def focused_layer(self):
        """Note: L.focused_layer = Layer() is equivalent to L.layers[L.focused_layer_idx] = Layer()."""
        if self._layers is not None:
            idx = self.focused_layer_idx
            if idx is not None:
                return self._layers[idx]

    @focused_layer.setter
    def focused_layer(self, v):
        idx = self.focused_layer_idx
        if idx is None:
            raise IndexError('No layer is currently focused.')
        self._layers[idx] = v

    def ensure_layer_focused(self):
        """If we have both a layer list & selection model and no Layer is selected & .layers is not empty:
           If there is a "current" layer, IE highlighted but not selected, select it.
           If there is no "current" layer, make .layer_stack[0] current and select it."""
        ls = self._layers
        if not ls:
            return
        sm = self._selection_model
        m = sm.model()
        if not sm.currentIndex().isValid():
            sm.setCurrentIndex(m.index(0, 0), Qt.QItemSelectionModel.SelectCurrent | Qt.QItemSelectionModel.Rows)
        if len(sm.selectedRows()) == 0:
            sm.select(sm.currentIndex(), Qt.QItemSelectionModel.SelectCurrent | Qt.QItemSelectionModel.Rows)

    @property
    def examine_layer_mode(self):
        return self.solo_layer_mode_action.isChecked()

    @examine_layer_mode.setter
    def examine_layer_mode(self, v):
        self.solo_layer_mode_action.setChecked(v)

    @property
    def auto_min_max_all(self):
        return self.auto_min_max_all_action.isChecked()

    @auto_min_max_all.setter
    def auto_min_max_all(self, v):
        self.auto_min_max_all_action.setChecked(v)

    @property
    def mask_radius(self):
        return self._mask_radius

    @mask_radius.setter
    def mask_radius(self, r):
        for layer in self.layers:
            layer.mask_radius = r

    def _attach_layers(self, layers):
        auto_min_max_all = self.auto_min_max_all
        for layer in layers:
            layer.mask_radius = self.mask_radius
            if auto_min_max_all:
                layer.auto_min_max = True
            # can connect without worrying that it's already connected because LayerList guarantees
            # that a given layer can only be in the lost
            layer.auto_min_max_changed.connect(self._on_layer_auto_min_max_changed)

    def _detach_layers(self, layers):
        for layer in layers:
            layer.auto_min_max_changed.disconnect(self._on_layer_auto_min_max_changed)

    def _on_inserting_into_layers(self, idx, layers):
        self._attach_layers(layers)

    def _on_removing_from_layers(self, idxs, layers):
        self._detach_layers(layers)

    def _on_replacing_in_layers(self, idxs, replaced_layers, layers):
        self._detach_layers(replaced_layers)
        self._attach_layers(layers)

    def _on_replaced_in_layers(self, idxs, replaced_layers, layers):
        # Note: the selection model may be associated with a proxy model, in which case this method's idxs argument is in terms of the proxy.  Therefore,
        # we can't use self.focused_layer_idx (if the selection model is attached to a proxy, self.focused_layer_idx is in terms of the proxied model,
        # not the proxy).
        focused_midx = self._selection_model.currentIndex()
        if focused_midx is None:
            return
        focused_row = focused_midx.row()
        try:
            change_idx = idxs.index(focused_row)
        except ValueError:
            return
        old_focused, focused = replaced_layers[change_idx], layers[change_idx]
        if old_focused is not focused:
            self.layer_focus_changed.emit(self, old_focused, focused)

    def _delayed_on_inserted_into_layers(self, idx, layers):
        self.ensure_layer_focused()

    def _delayed_on_removed_from_layers(self, idxs, layers):
        self.ensure_layer_focused()

    def _on_current_row_changed(self, midx, old_midx):
        # TODO: verify that this happens in response to signaling list removing signal and not removed signal
        sm = self._selection_model
        m = sm.model()
        ls = self._layers
        if isinstance(m, Qt.QAbstractProxyModel):
            if old_midx.isValid():
                old_midx = m.mapToSource(old_midx)
            if midx.isValid():
                midx = m.mapToSource(midx)
        ol = ls[old_midx.row()] if old_midx.isValid() else None
        l = ls[midx.row()] if midx.isValid() else None
        if l is not ol:
            self.layer_focus_changed.emit(self, ol, l)

    def _on_master_enable_auto_min_max_triggered(self, checked):
        # Disable auto min/max for all Layers in this LayerStack when auto min/max is explicitly deactivated but not when auto min/max is deactivated as
        # a result of assignment to a constituent Layer's min or max properties.
        if not checked:
            for layer in self.layers:
                layer.auto_min_max = False

    def _on_master_enable_auto_min_max_toggled(self, checked):
        if checked and self._layers:
            for layer in self._layers:
                layer.auto_min_max = True

    def _on_layer_auto_min_max_changed(self, layer):
        if self.auto_min_max_all and not layer.auto_min_max:
            self.auto_min_max_all = False

