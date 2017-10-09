# The MIT License (MIT)
#
# Copyright (c) 2016 WUSTL ZPLAB
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

from PyQt5 import Qt
from .. import shared_resources

class LayerStackPainterBrush:
    def __init__(self, color, mask, center):
        self.color = color
        self.mask = mask
        self.center = center

    def apply(self, target_subimage, brush_subrect):
        br = brush_subrect
        m = self.mask[br.left():br.right()+1,br.top():br.bottom()+1]
        target_subimage[m] = self.color

class LayerStackPainterItem(Qt.QGraphicsObject):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    # Something relevant to LayerStackPainter changed: either we are now looking at a different Image
    # instance due to assignment to layer.image, or image data type and/or channel count and/or range
    # changed.  target_image_changed is not emitted when just image data changes.
    target_image_changed = Qt.pyqtSignal(Qt.QObject)

    def __init__(self, layer_stack_item):
        super().__init__(layer_stack_item)
        self.setFlag(Qt.QGraphicsItem.ItemHasNoContents)
        self._boundingRect = Qt.QRectF()
        self.layer_stack_item = layer_stack_item
        layer_stack_item.bounding_rect_changed.connect(self._on_layer_stack_item_bounding_rect_changed)
        layer_stack_item.layer_stack.layers_replaced.connect(self._on_layers_replaced)
        layer_stack_item.layer_stack.layer_focus_changed.connect(self._on_layer_changed)
        self.layer_stack = layer_stack_item.layer_stack
        self._target_layer_idx = None
        self.target_layer = None
        self.target_image = None
        self._connect_layers(self.layer_stack.layers)
        self._on_layer_stack_item_bounding_rect_changed()
        self.brush = None
        self.alternate_brush = None
        layer_stack_item.installSceneEventFilter(self)

    def boundingRect(self):
        return self._boundingRect

    def sceneEventFilter(self, watched, event):
        if not (self.isVisible()
                and self.target_image is not None
                and event.type() in {Qt.QEvent.GraphicsSceneMousePress, Qt.QEvent.GraphicsSceneMouseMove}
                and event.buttons() == Qt.Qt.RightButton
                and event.modifiers() in (Qt.Qt.ShiftModifier, Qt.Qt.NoModifier)):
            return False

        brush = self.brush if event.modifiers() == Qt.Qt.NoModifier else self.alternate_brush
        if brush is None:
            return False

        p = self.mapFromScene(event.scenePos())
        target_size = self.target_image.size
        target_width = target_size.width()
        target_height = target_size.height()
        if self._boundingRect.toRect().size() != target_size:
            p.setX(p.x() * target_width / bounding_size.width())
            p.setY(p.y() * target_height / bounding_size.height())

        p = Qt.QPoint(p.x(), p.y())
        r = Qt.QRect(p.x(), p.y(), *brush.mask.shape)
        r.translate(-brush.center[0], -brush.center[1])
        if not r.intersects(Qt.QRect(Qt.QPoint(), target_size)):
            return False

        br = Qt.QRect(0, 0, *brush.mask.shape)
        if r.left() < 0:
            br.setLeft(-r.x())
            r.setLeft(0)
        if r.top() < 0:
            br.setTop(-r.y())
            r.setTop(0)
        if r.right() >= target_width:
            br.setRight(br.right() - (r.right() - target_width + 1))
            r.setRight(target_width - 1)
        if r.bottom() >= target_height:
            br.setBottom(br.bottom() - (r.bottom() - target_height + 1))
            r.setBottom(target_height - 1)
        brush.apply(self.target_image.data[r.left():r.right()+1, r.top():r.bottom()+1], br)
        self.target_image.refresh()
        return True

    def _on_layer_stack_item_bounding_rect_changed(self):
        self.prepareGeometryChange()
        self._boundingRect = self.layer_stack_item.boundingRect()

    def _on_layers_replaced(self, layer_stack, old_layers, layers):
        assert layer_stack is self.layer_stack and self.layers is old_layers
        old_layers.inserted.disconnect(self._on_layer_changed)
        old_layers.removed.disconnect(self._on_layer_changed)
        old_layers.replaced.disconnect(self._on_layer_changed)
        self._connect_layers(layers)

    def _connect_layers(self, layers):
        self.layers = layers
        layers.inserted.connect(self._on_layer_changed)
        layers.removed.connect(self._on_layer_changed)
        layers.replaced.connect(self._on_layer_changed)
        self._on_layer_changed()

    def _on_layer_changed(self):
        target_layer = self.layer_stack.focused_layer
        if target_layer is self.target_layer:
            return
        if self.target_layer is not None:
            self.target_layer.image_changed.disconnect(self._on_image_changed)
        self.target_layer = target_layer
        if target_layer is not None:
            target_layer.image_changed.connect(self._on_image_changed)
        self._on_image_changed()

    def _on_image_changed(self):
        new_target = None if self.target_layer is None else self.target_layer.image
        if self.target_image is not new_target:
            self.target_image = new_target
            self.setVisible(new_target is not None) # hide if target goes to None
            self.target_image_changed.emit(self)
