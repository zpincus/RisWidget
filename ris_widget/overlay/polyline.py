# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .. import shared_resources
from . import point_set

class _PolylinePointHandle(point_set._PointHandle):
    def __init__(self, parent, layer_stack, color):
        super().__init__(parent, layer_stack, color)
        self._set_active(False)

    def _set_active(self, active):
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable, active)
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable, active)


class Polyline(point_set.PointSet):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    POINT_TYPE = _PolylinePointHandle

    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None,
        on_geometry_change=None):
        self._active_drawing = False
        self._last_pos = None
        super().__init__(ris_widget, color, geometry, on_geometry_change, max_points=None)

    @point_set.PointSet.geometry.setter
    def geometry(self, geometry):
        point_set.PointSet.geometry.fset(self, geometry)
        # start out in non-drawing state if geometry is defined, otherwise start active
        if geometry is None:
            self._set_drawing(True)
        else:
            self._set_drawing(False)

    def _generate_path(self):
        positions = []
        # filter duplicates
        for point in self.points:
            pos = point.pos()
            if len(positions) == 0 or pos != positions[-1]:
                positions.append(pos)
        if (self._active_drawing and self._last_pos is not None
                and len(positions) > 0 and self._last_pos != positions[-1]):
            positions.append(self._last_pos)
        self.setPath(self._generate_path_from_positions(positions))

    @staticmethod
    def _generate_path_from_positions(positions):
        if len(positions) == 0:
            path = Qt.QPainterPath()
        else:
            path = Qt.QPainterPath(positions[0])
            for pos in positions[1:]:
                path.lineTo(pos)
        return path

    def _set_drawing(self, drawing):
        self._active_drawing = drawing
        for point in self.points:
            point._set_active(not drawing)
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable, not drawing)
        self._generate_path()

    def _insert_point(self, pos):
        # TODO: insert point between nearest control points
        pass

    def _view_mouse_release(self, pos, modifiers):
        # Called when ROI item is visible, and a mouse-up on the underlying
        # view occurs. (I.e. not on this item itself)
        if self._active_drawing:
            if len(self.points) > 0:
                diff = self.points[-1].pos() - pos
                sqdist = diff.x()**2 + diff.y()**2
                if sqdist < 4:
                    self._set_drawing(False)
                    return
            self._add_point(pos)
        elif modifiers & Qt.Qt.AltModifier:
            self._insert_point(pos)

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.Qt.AltModifier:
            self._insert_point(event.pos())
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # QGraphicsItem's default mouseReleaseEvent deselects all other items in the scene,
        # but we want the handles to stay selected.
        pass

    def _geometry_changed(self):
        self._generate_path()
        super()._geometry_changed()

    def _selected(self):
        super()._selected()
        for point in self.points:
            point.setSelected(True)

    def _deselected(self):
        super()._deselected()
        for point in self.points:
            point.setSelected(False)

    def _delete_selected(self):
        if self.isSelected():
            self.geometry = None
        else:
            super()._delete_selected()
            if len(self.points) == 0:
                self._set_drawing(True)

    def sceneEventFilter(self, watched, event):
        event_type = event.type()
        if event_type == Qt.QEvent.GraphicsSceneHoverMove:
            # record even if not actively drawing, so slash-key press can draw line to
            # current mouse pos...
            self._last_pos = event.pos()
        if self._active_drawing:
            if event_type == Qt.QEvent.GraphicsSceneHoverMove:
                self._generate_path()
                return False # let the rest of the scene see the hover move too (i.e. update the mouseover text)
            elif event_type == Qt.QEvent.GraphicsSceneMouseDoubleClick:
                self._set_drawing(False)
                return True
            elif event_type == Qt.QEvent.KeyPress:
                key = event.key()
                if key == Qt.Qt.Key_Escape:
                    self._set_drawing(False)
                    return True
                elif key in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}:
                    if len(self.points) > 0:
                        self.points.pop().remove()
                        if len(self.points) == 0:
                            self._last_pos = None
                        self._geometry_changed()
                        return True
        else: # not active drawing
            if event_type == Qt.QEvent.KeyPress:
                key = event.key()
                if key == Qt.Qt.Key_Slash:
                    self._set_drawing(True)
                    return True
                elif key in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}:
                    self._delete_selected()
                    return True
        return False