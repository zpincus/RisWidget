# This code is licensed under the MIT License (see LICENSE file for details)

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
            return layer.Layer(obj)
        elif isinstance(obj, layer.Layer):
            return obj
        else:
            raise TypeError("All inputs must be numpy.ndarray, Image, or Layer")

class LayerStack(Qt.QObject):
    """LayerStack: The owner of a LayerList (L.layers, in ascending order, with bottom layer - ie, backmost - as element 0) and selection model that is
    referenced by various other objects such as LayerStackItem, LayerTable, RisWidget, and Flipbooks.

    Signals:
    * layer_focus_changed(layer_stack, old_focused_layer, focused_layer): layer_stack.focused_layer changed from old_focused layer to focused_layer,
    its current value.
    * focused_image_changed(old_focused_image, focused_image): The image of the currently-focused layer has changed, either because the foused layer
    itself has changed, or the image in that layer was replaced or modified in-place.

    """
    layer_focus_changed = Qt.pyqtSignal(Qt.QObject, object, object)
    focused_image_changed = Qt.pyqtSignal(object)

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
        self.layer_focus_changed.connect(self._on_layer_focus_changed)

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

        self.layers.append(layer.Layer())

    @property
    def layers(self):
        return self._layers

    @layers.setter
    def layers(self, new_layers):
        num_new_layers = len(new_layers)
        num_extant_layers = len(self._layers)
        for i in range(max(num_new_layers, num_extant_layers)):
            if i >= num_new_layers:
                self._layers[i].image = None
            elif i >= num_extant_layers:
                self._layers.append(new_layers[i])
            else:
                new_layer = new_layers[i]
                if isinstance(new_layer, layer.Layer):
                    self._layers[i] = new_layer
                else:
                    self._layers[i].image = new_layer


    def set_selection_model(self, selection_model):
        assert isinstance(selection_model, Qt.QItemSelectionModel)
        if self._selection_model is not None:
            raise RuntimeError('only set selection model once, immediately after construction')
        selection_model.currentRowChanged.connect(self._on_current_row_changed)
        self._selection_model = selection_model

    @property
    def focused_layer_idx(self):
        sm = self._selection_model
        if self._selection_model is None:
            return None
        m = self._selection_model.model()
        midx = sm.currentIndex()
        if isinstance(m, Qt.QAbstractProxyModel):
            # Selection model is with reference to table view's model, which is a proxy model (probably an InvertingProxyModel)
            if not midx.isValid():
                return None
            midx = m.mapToSource(midx)
        if midx.isValid():
            return midx.row()

    @property
    def focused_layer(self):
        """Note: L.focused_layer = Layer() is equivalent to L.layers[L.focused_layer_idx] = Layer()."""
        idx = self.focused_layer_idx
        return None if idx is None else self._layers[idx]

    @focused_layer.setter
    def focused_layer(self, v):
        idx = self.focused_layer_idx
        if idx is None:
            raise IndexError('No layer is currently focused.')
        self._layers[idx] = v

    @property
    def focused_image(self):
        idx = self.focused_layer_idx
        return None if idx is None else self._layers[idx].image


    def ensure_layer_focused(self):
        """If we have both a layer list & selection model and no Layer is selected & .layers is not empty:
           If there is a "current" layer, IE highlighted but not selected, select it.
           If there is no "current" layer, make .layer_stack[0] current and select it."""
        sm = self._selection_model
        if sm is None:
            return
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
        if self._selection_model is None:
            return
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
        # NB: There is a race condition when a layer is removed right before the ris_widget itself
        # is deleted. If ensure_layer_focused runs after ris_widget goes away, then it fails
        # because some qt objects have been deleted on the C++ side. This is generally rare, though,
        # and doesn't break things (it just prints a stack trace), so it's a low priority TODO
        self.ensure_layer_focused()

    def _on_current_row_changed(self, midx, old_midx):
        # TODO: verify that this happens in response to signaling list removing signal and not removed signal
        if self._selection_model is None:
            return
        m = self._selection_model.model()
        if isinstance(m, Qt.QAbstractProxyModel):
            if old_midx.isValid():
                old_midx = m.mapToSource(old_midx)
            if midx.isValid():
                midx = m.mapToSource(midx)
        old_layer = self._layers[old_midx.row()] if old_midx.isValid() else None
        new_layer = self._layers[midx.row()] if midx.isValid() else None
        if new_layer is not old_layer:
            self.layer_focus_changed.emit(self, old_layer, new_layer)

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

    def _on_layer_focus_changed(self, layer_stack, old_focused_layer, focused_layer):
        if old_focused_layer is not None:
            old_focused_layer.image_changed.disconnect(self._on_focused_layer_image_changed)
        if focused_layer is not None:
            focused_layer.image_changed.connect(self._on_focused_layer_image_changed)
        image = None if focused_layer is None else focused_layer.image
        self.focused_image_changed.emit(image)

    def _on_focused_layer_image_changed(self, focused_layer):
        self.focused_image_changed.emit(focused_layer.image)


