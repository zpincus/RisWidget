from PyQt5 import Qt

from .. import shared_resources
from . import point_set

class _PolylinePointHandle(point_set._PointHandle):
    def __init__(self, parent, color):
        super().__init__(parent, color)
        self._set_active(False)

    def _set_active(self, active):
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable, active)
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
            self._start_drawing()
        else:
            self._end_drawing()

    def _generate_path(self):
        if len(self.points) == 0:
            path = Qt.QPainterPath()
        else:
            path = Qt.QPainterPath(self.points[0])
            for point in self.points[1:]:
                path.lineTo(point)
            if self._last_pos is not None:
                path.lineTo(last)
        self.setPath(path)

    def _end_drawing(self):
        self._generate_path()
        self._set_drawing(False)

    def _start_drawing(self):
        self._set_drawing(True)

    def _set_drawing(self, drawing):
        self._last_pos = None
        self._active_drawing = drawing
        for point in self.points:
            point._set_active(not drawing)
        self._set_active(not drawing)

    def _view_mouse_release(self, pos):
        # Called when ROI item is visible, and a mouse-up on the underlying
        # view occurs. (I.e. not on this item itself)
        if self._active_drawing:
            if len(self.points) > 0:
                diff = self.points[-1].pos() - pos
                sqdist = diff.x()**2 + diff.y()**2
                if sqdist < 4:
                    self._end_drawing()
                    return
            self.add_point(pos)
            self._generate_path()

    def sceneEventFilter(self, watched, event):
        if self._active_drawing:
            if event.type() == Qt.QEvent.GraphicsSceneHoverMove:
                self._last_pos = event.pos()
                self._generate_path()
                return True
            elif event.type() == Qt.QEvent.KeyPress:
                key = event.key()
                if key == Qt.Qt.Key_Escape:
                    self._end_drawing()
                    return True
                elif key in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}:
                    self.points.pop()
                    self._geometry_changed()
                    if len(self.points) == 0:
                        self._end_drawing() # calls _generate_path() itself
                    else:
                        self._generate_path()
                    return True
        else: # not active drawing
            if event.type() == Qt.QEvent.KeyPress:
                key = event.key()
                if key == Qt.Qt.Key_Slash:
                    self._start_drawing()

            # TODO: option / alt click inserts point
            # TODO: +/- for subdivide / downsample
        return False