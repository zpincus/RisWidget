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
        self.setFlag(Qt.QGraphicsItem.ItemIsFocusable, active) # Necessary in order for item to receive keyboard events
        self.setFlag(Qt.QGraphicsItem.ItemSendsGeometryChanges, active) # Necessary in order for .itemChange to be called when item is moved


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
        # start out in non-drawing state if geometry is defined
        if geometry is None:
            self._set_drawing(True)
        else:
            self._set_drawing(False)

    def _generate_path(self):
        if len(self.points) == 0:
            path = Qt.QPainterPath()
        else:
            path = Qt.QPainterPath(self.points[0].pos())
            for point in self.points[1:]:
                path.lineTo(point.pos())
            if self._active_drawing and self._last_pos is not None:
                path.lineTo(self._last_pos)
        self.setPath(path)

    def _set_drawing(self, drawing):
        self._active_drawing = drawing
        for point in self.points:
            point._set_active(not drawing)
        self._set_active(not drawing)
        self._generate_path()

    def _view_mouse_release(self, pos):
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

    def _geometry_changed(self):
        super()._geometry_changed()
        self._generate_path()

    def _selected(self):
        super()._selected()
        for point in self.points:
            point.setSelected(True)

    def _deselected(self):
        super()._deselected()
        for point in self.points:
            point.setSelected(False)

    def _delete_selected(self):
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

            # TODO: option / alt click inserts point
            # TODO: +/- for subdivide / downsample
        return False