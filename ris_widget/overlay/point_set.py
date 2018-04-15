# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .. import shared_resources
from . import base

class _PointHandle(base.SelectableHandle):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, point_set, pos, brush, pen=None):
        self._geometry_changed = point_set._geometry_changed
        layer_stack = point_set.parentItem()
        super().__init__(layer_stack, layer_stack, brush, pen)
        self.setPos(pos)
        self.setFlag(Qt.QGraphicsItem.ItemSendsGeometryChanges) # Necessary in order for .itemChange to be called when item is moved

    def itemChange(self, change, value):
        if change == Qt.QGraphicsItem.ItemPositionHasChanged:
            self._geometry_changed()
        else:
            return super().itemChange(change, value)

class PointSet(base.RWGeometryItemMixin, Qt.QGraphicsPathItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    POINT_TYPE = _PointHandle

    # just need to inherit from some QGraphicsItem that can have a pen set
    def __init__(self, ris_widget, brush=None, pen=None, geometry=None, max_points=None):
        self.max_points = max_points
        self.points = []
        self._last_click_deselected = False
        if brush is None:
            brush = Qt.Qt.green
        self.brush = brush
        self.pen = pen
        super().__init__(ris_widget, geometry=geometry)

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
                self._add_point(Qt.QPointF(x, y))

    def _add_point(self, pos):
        if self.max_points is None or len(self.points) < self.max_points:
            self.points.append(self.POINT_TYPE(self, pos, self.brush, self.pen))
            return True
        return False

    def _delete_selected(self):
        new_points = []
        deleted = False
        for point in self.points:
            if point.isSelected():
                point.remove()
                deleted = True
            else:
                new_points.append(point)
        self.points = new_points
        if deleted:
            self._geometry_changed()

    def remove(self):
        for point in self.points:
            point.remove()
        super().remove()

    def _view_mouse_release(self, pos, modifiers):
        # Called when item is visible, and a mouse-up on the underlying
        # view occurs. (I.e. not on this item itself)
        if not self._last_click_deselected:
            if self._add_point(pos):
                self._geometry_changed()

    def sceneEventFilter(self, watched, event):
        event_type = event.type()
        if event_type == Qt.QEvent.GraphicsSceneMousePress and event.button() == Qt.Qt.LeftButton:
            if any(point.isSelected() for point in self.points):
                self._last_click_deselected = True
            else:
                self._last_click_deselected = False
            # don't return true to not swallow the mouse click
        elif (event_type == Qt.QEvent.KeyPress and event.key() in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace} and
                any(point.isSelected() for point in self.points)):
            self._delete_selected()
            return True
        return False


