# This code is licensed under the MIT License (see LICENSE file for details)

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
    # instance due to assignment to layer.image, or due to a change in the focused layer.
    target_image_changed = Qt.pyqtSignal(Qt.QObject)

    def __init__(self, layer_stack_item):
        super().__init__(layer_stack_item)
        self.setFlag(Qt.QGraphicsItem.ItemHasNoContents)
        self.layer_stack_item = layer_stack_item
        self.target_image = None
        self.brush = None
        self.alternate_brush = None
        self.left_click_draws = False
        layer_stack_item.layer_stack.focused_image_changed.connect(self._on_focused_image_changed)
        self._on_focused_image_changed(layer_stack_item.layer_stack.focused_image)
        layer_stack_item.bounding_rect_changed.connect(self._on_layer_stack_item_bounding_rect_changed)
        self._on_layer_stack_item_bounding_rect_changed()
        layer_stack_item.installSceneEventFilter(self)

    def boundingRect(self):
        return Qt.QRectF()

    def _brush_for_click(self, event):
        buttons = event.buttons()
        modifiers = event.modifiers()
        valid = False
        if self.left_click_draws and buttons == Qt.Qt.LeftButton and not modifiers & Qt.Qt.AltModifier:
            # if alt is held down, don't try to draw but instead forward the drag/click to the layer stack
            # to pan the view
            valid = True
        elif not self.left_click_draws and buttons == Qt.Qt.LeftButton and modifiers & Qt.Qt.MetaModifier:
            valid = True
        elif not self.left_click_draws and buttons == Qt.Qt.RightButton:
            valid = True
        if not valid:
            return None
        if modifiers & Qt.Qt.ShiftModifier:
            return self.alternate_brush
        else:
            return self.brush

    def sceneEventFilter(self, watched, event):
        if not (self.isVisible() and self.target_image is not None and
                event.type() in {Qt.QEvent.GraphicsSceneMousePress, Qt.QEvent.GraphicsSceneMouseMove}):
            return False

        brush = self._brush_for_click(event)
        if brush is None:
            return False

        p = self.mapFromScene(event.scenePos())
        target_size = self.target_image.size
        target_width = target_size.width()
        target_height = target_size.height()

        if self.bounding_size != target_size:
            p.setX(p.x() * target_width / self.bounding_size.width())
            p.setY(p.y() * target_height / self.bounding_size.height())

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
        x1, x2, y1, y2 = r.left(), r.right(), r.top(), r.bottom()
        brush.apply(self.target_image.data[x1:x2+1, y1:y2+1], br)
        w = x2 - x1
        h = y2 - y1
        self.target_image.refresh((x1, y1, w, h))
        return True

    def _on_layer_stack_item_bounding_rect_changed(self):
        self.bounding_size = self.layer_stack_item.boundingRect().toRect().size()

    def _on_focused_image_changed(self, new_image):
        if self.target_image is not new_image:
            self.target_image = new_image
            self.setVisible(new_image is not None) # hide if target goes to None
            self.target_image_changed.emit(self)
