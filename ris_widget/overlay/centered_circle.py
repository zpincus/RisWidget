# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .. import shared_resources
from . import base

class _CenterHandle(base.SelectableHandle):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, parent, layer_stack, color):
        super().__init__(parent, layer_stack, color)
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable, False)

    def _selected(self):
        super()._selected()
        self.parentItem().setSelected(True)

    def _deselected(self):
        super()._deselected()
        self.parentItem().setSelected(False)

    def mouseMoveEvent(self, event):
        pos = self.mapToParent(event.pos())
        self.parentItem()._center_moved(pos.x(), pos.y())

class CenteredCircle(base.RWGeometryItemMixin, Qt.QGraphicsEllipseItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, pen=None, geometry=None):
        self._handle = None # need stub handle
        super().__init__(ris_widget, pen, geometry=None)
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable)
        self._handle = _CenterHandle(self, self.parentItem(), self.pen().color())
        self.geometry = geometry # can only set non-none geometry after we have self._handle

    @property
    def geometry(self):
        if self._radius is None:
            return None
        else:
            return self._cx, self._cy, self._radius

    @geometry.setter
    def geometry(self, geometry):
        if geometry is None:
            self._radius = self._cx = self._cy = None
        else:
            self._cx, self._cy, self._radius = geometry
        self.setSelected(False)
        self._update()

    def _center_moved(self, cx, cy):
        self._cx = cx
        self._cy = cy
        self._update()

    def _update(self):
        r = self._radius
        if r is None:
            self.setRect(0, 0, 0, 0)
            if self._handle is not None:
                self._handle.hide()
        else:
            self._handle.show()
            self._handle.setPos(self._cx, self._cy)
            self.setRect(Qt.QRectF(self._cx-r, self._cy-r, 2*r, 2*r))
        self._geometry_changed()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()
        self._radius = ((x-self._cx)**2 + (y-self._cy)**2)**0.5
        self._update()

    def _selected(self):
        super()._selected()
        self._handle.setSelected(True)

    def _deselected(self):
        super()._deselected()
        self._handle.setSelected(False)