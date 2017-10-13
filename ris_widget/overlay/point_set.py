from PyQt5 import Qt

from .. import shared_resources
from . import base

class _PointHandle(base.SelectableHandle):
    def __init__(self, parent, layer_stack, color):
        super().__init__(parent, layer_stack, color)
        self.setFlag(Qt.QGraphicsItem.ItemIsFocusable) # Necessary in order for item to receive keyboard events
        self.setFlag(Qt.QGraphicsItem.ItemSendsGeometryChanges) # Necessary in order for .itemChange to be called when item is moved

    def itemChange(self, change, value):
        if change == Qt.QGraphicsItem.ItemPositionHasChanged:
            self.parentItem()._geometry_changed()
        else:
            return super().itemChange(change, value)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}:
            self.parentItem()._delete_selected()

class PointSet(base.RWGeometryItemMixin, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    POINT_TYPE = _PointHandle

    # just need to inherit from some QGraphicsItem that can have a pen set
    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None,
        on_geometry_change=None, max_points=None):
        self.max_points = max_points
        self.color = color
        self.points = []
        self._last_click_deselected = False
        super().__init__(ris_widget, color, geometry, on_geometry_change)
        self.parentItem().installSceneEventFilter(self)

    @property
    def geometry(self):
        if len(self.points) == 0:
            geometry = None
        else:
            geometry = []
            for point in self.points:
                pos = point.pos()
                geometry.append([pos.x(), pos.y()])
        return geometry

    @geometry.setter
    def geometry(self, geometry):
        for point in self.points:
                point.remove()
        self.points = []
        if geometry is not None:
            for x, y in geometry:
                self._add_point(Qt.QPointF(x, y), skip_change=True)
        self._geometry_changed()

    def _add_point(self, pos, skip_change=False):
        if self.max_points is None or len(self.points) < self.max_points:
            point = self.POINT_TYPE(self, self.parentItem(), self.color)
            point.setPos(pos)
            self.points.append(point)
            if not skip_change:
                self._geometry_changed()

    def _delete_selected(self):
        new_points = []
        for point in self.points:
            if point.isSelected():
                point.remove()
            else:
                new_points.append(point)
        self.points = new_points
        self._geometry_changed()

    def remove(self):
        self.parentItem().removeSceneEventFilter(self)
        for point in self.points:
            point.remove()
        super().remove()

    def _view_mouse_release(self, pos):
        # Called when ROI item is visible, and a mouse-up on the underlying
        # view occurs. (I.e. not on this item itself)
        if not self._last_click_deselected:
            self._add_point(pos)

    def sceneEventFilter(self, watched, event):
        if event.type() == Qt.QEvent.GraphicsSceneMousePress and event.button() == Qt.Qt.LeftButton:
            if any(point.isSelected() for point in self.points):
                self._last_click_deselected = True
            else:
                self._last_click_deselected = False
        return False


