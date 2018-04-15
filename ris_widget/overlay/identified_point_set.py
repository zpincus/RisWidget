# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .. import shared_resources
from . import point_set

class _NoPoint:
    def isSelected(self):
        return False

    def remove(self):
        pass

NO_POINT = _NoPoint()

class IdentifiedPointSet(point_set.PointSet):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()

    def __init__(self, ris_widget, num_points, colors=None, pen=None, geometry=None):
        if colors is None:
            colors = [Qt.Qt.green] * num_points
        assert len(colors) == num_points
        self.colors = colors
        super().__init__(ris_widget, pen=pen, geometry=geometry, max_points=num_points)

    @property
    def geometry(self):
        geometry = []
        for point in self.points:
            if point is NO_POINT:
                point_geom = None
            else:
                pos = point.pos()
                point_geom = pos.x(), pos.y()
            geometry.append(point_geom)
        return geometry

    @geometry.setter
    def geometry(self, geometry):
        for point in self.points:
            point.remove()
        self.points = []
        if geometry is None:
            geometry = [None] * self.max_points
        if len(geometry) != self.max_points:
            raise ValueError('Incorrect number of points specified')
        for i, point in enumerate(geometry):
            if point is None:
                self.points.append(NO_POINT)
            else:
                x, y = point
                pos = Qt.QPointF(x, y)
                self.points.append(self.POINT_TYPE(self, pos, self.colors[i], self.pen))

    def _add_point(self, pos):
        try:
            i = self.points.index(NO_POINT)
        except ValueError:
            # no more points to add
            return False
        self.points[i] = self.POINT_TYPE(self, pos, self.colors[i], self.pen)
        return True

    def _delete_selected(self):
        deleted = False
        for i, point in enumerate(self.points):
            if point.isSelected():
                deleted = True
                point.remove()
                self.points[i] = NO_POINT
        if deleted:
            self._geometry_changed()