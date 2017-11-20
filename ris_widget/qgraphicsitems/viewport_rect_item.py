# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

class ViewportRectItem(Qt.QGraphicsObject):
    size_changed = Qt.pyqtSignal(Qt.QSizeF)

    def __init__(self):
        super().__init__()
        self.setFlags(
            Qt.QGraphicsItem.ItemIgnoresTransformations |
            Qt.QGraphicsItem.ItemSendsGeometryChanges |
            Qt.QGraphicsItem.ItemSendsScenePositionChanges |
            Qt.QGraphicsItem.ItemHasNoContents
        )
        self._size = Qt.QSizeF()
        # Children are generally overlay items that should appear over anything else rather than z-fighting
        self.setZValue(10)

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, v):
        if not isinstance(v, Qt.QSizeF):
            v = Qt.QSizeF(v)
        if self._size != v:
            self.prepareGeometryChange()
            self._size = v
        self.size_changed.emit(v)

    def boundingRect(self):
        return Qt.QRectF(Qt.QPointF(), self._size)

