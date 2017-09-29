# The MIT License (MIT)
#
# Copyright (c) 2014-2016 WUSTL ZPLAB
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
# Authors: Zach Pincus
"""
Example 1: Simple ROI drawing
    roi = RectROI(rw)
    # click to draw ROI in GUI
    (x1, y1), (x2, y2) = roi.geometry
    roi.remove()

Example 2: Pre-set bounds with a specified aspect ratio (width/height):
    roi = EllipseROI(rw, aspect=2, geometry=((200, 400), (600, 500)))
"""

import itertools
from PyQt5 import Qt

from .. import shared_resources
from . import shared


class _ROIMixin(shared.RWGeometryItemMixin):
    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None,
        on_geometry_change=None, aspect=None):
        """Class for drawing a Region of Interest on a ris_widget.

        The ROI can be drawn by clicking on the upper-left of the desired region,
        then dragging. A second click sets the lower-right. Pressing escape
        before this allows selection of a new upper-left point.

        Afterward, the ROI can be clicked to highlight it, allowing movement or
        resizing. Pressing delete/backspace will remove a selected ROI and allow
        it to be re-drawn.

        The geometry property can be used to obtain the ((x1, y1), (x2, y2))
        positions of the corners of the ROI. If no ROI is shown, this will be None.

        To remove from the ris_widget, call remove().

        Parameters:
            ris_widget: a ris_widget instance to draw an ROI on
            color: a Qt color for the ROI
            geometry: ((x1, y1), (x2, y2)) coordinates of upper-left and lower-
                right corners. If None, the ROI can be drawn by clicking.
            on_geometry_change: callback that will be called with new geometry,
                or None if the ROI is removed.
            aspect: width/height ratio to maintain, or None
        """
        self.aspect = aspect
        super().__init__(ris_widget, color, geometry, on_geometry_change)
        self.dragging = False
        self.parentItem().installSceneEventFilter(self)
        self.handles = {_ResizeHandle(self, Qt.Qt.red): coords for coords in [
            (0, 0),
            (0.5, 0),
            (1, 0),
            (1, 0.5),
            (1, 1),
            (0.5, 1),
            (0, 1),
            (0, 0.5)
        ]}

    def remove(self):
        for handle in self.handles:
            handle.remove()
        self.parentItem().removeSceneEventFilter(self)
        super().remove()

    @property
    def geometry(self):
        rect = self.rect()
        if rect.isValid():
            x1, y1, x2, y2 = rect.normalized().getCoords()
            return (x1, y1), (x2, y2)
        else:
            return None

    @geometry.setter
    def geometry(self, geometry):
        self.setSelected(False)
        self._set_geometry(geometry)

    def _set_geometry(self, geometry):
        self.dragging = False
        if geometry is None:
            self.setRect(0, 0, 0, 0)
            self.setFlag(Qt.QGraphicsItem.ItemIsSelectable, False)
        else:
            (x1, y1), (x2, y2) = geometry
            rect = Qt.QRectF()
            rect.setCoords(x1, y1, x2, y2)
            self.setRect(self._aspect_adjusted_rect(rect).normalized())
            self.setFlag(Qt.QGraphicsItem.ItemIsSelectable)
        if self.on_geometry_change is not None:
            self.on_geometry_change(geometry)

    def _aspect_adjusted_rect(self, rect):
        if self.aspect is not None:
            desired_height = rect.width() / self.aspect
            rect.setHeight(desired_height)
        return rect

    def _view_mouse_release(self, pos):
        # Called when ROI item is visible, and a mouse-up on the underlying
        # view occurs. (I.e. not on this item itself)
        if not self.rect().isValid():
            # no current ROI shown: start a new one
            self.dragging = True
            self.setRect(Qt.QRectF(pos, pos))
        elif self.dragging:
            # finish drawing the roi_rect. _done_resizing will handle making
            # it selectable
            self._done_resizing() # sets dragging false via setting self.geometry

    def sceneEventFilter(self, watched, event):
        if self.dragging:
            if event.type() == Qt.QEvent.GraphicsSceneHoverMove:
                # just a resize event: don't call on_geometry_change until done with dragging
                rect = self.rect()
                rect.setBottomRight(event.pos())
                self.setRect(self._aspect_adjusted_rect(rect))
                return True
            elif event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Escape:
                self.geometry = None # this sets dragging false
                return True
        elif (self.isSelected() and event.type() == Qt.QEvent.KeyPress
              and event.key() in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}):
            self.geometry = None
            return True
        return False

    def _done_resizing(self):
        # called after resize. set self.geometry to clean up position and call on_geometry_change
        x1, y1, x2, y2 = self.rect().getCoords()
        # call _set_geometry rather than setting .geometry property to keep selected state
        self._set_geometry(((x1, y1), (x2, y2)))

    def _reposition_handles(self):
        rect = self.rect()
        ul = rect.topLeft()
        vector = rect.bottomRight() - ul
        for handle, coords in self.handles.items():
            x = ul.x() + vector.x() * coords[0]
            y = ul.y() + vector.y() * coords[1]
            handle.setPos(x, y)

    def _selected(self):
        super()._selected()
        self._reposition_handles()
        for handle in self.handles:
            handle.show()

    def _deselected(self):
        super()._deselected()
        for handle in self.handles:
            handle.hide()

    def mouseMoveEvent(self, event):
        # called during a drag on the ROI itself, not on a handle corner.
        # Ordinarily we would just let Qt handle this, but we need to also move
        # the resize corners...
        delta = event.pos() - event.lastPos()
        self.setRect(self.rect().translated(delta.x(), delta.y()))
        self._reposition_handles()

    def mouseReleaseEvent(self, event):
        # called after a drag on the ROI itself, not on a handle corner
        self._done_resizing()

    def _handle_moved(self, pos, handle):
        # called during handle dragging: don't call on_geometry_change
        xc, yc = self.handles[handle]
        rect = self.rect()
        x1, y1, x2, y2 = rect.getCoords()
        x = [x1, x2]
        y = [y1, y2]
        if xc != 0.5:
            x[xc] = pos.x()
        if yc != 0.5:
            y[yc] = pos.y()

        if self.aspect is not None:
            if xc == 0.5: # trying to adjust height only, so servo width to maintain aspect
                desired_width = (y[1] - y[0]) * self.aspect
                x[1] = x[0] + desired_width
            else:
                desired_height = (x[1] - x[0]) / self.aspect
                if yc != 0:
                    y[1] = y[0] + desired_height
                else:
                    y[0] = y[1] - desired_height

        rect.setCoords(x[0], y[0], x[1], y[1])
        self.setRect(rect)
        self._reposition_handles()


class RectROI(_ROIMixin, Qt.QGraphicsRectItem):
    QGRAPHICSITEM_TYPE = shared_resources.UNIQUE_QGRAPHICSITEM_TYPE()

    def type(self):
        return self.QGRAPHICSITEM_TYPE


class EllipseROI(_ROIMixin, Qt.QGraphicsEllipseItem):
    QGRAPHICSITEM_TYPE = shared_resources.UNIQUE_QGRAPHICSITEM_TYPE()

    def type(self):
        return self.QGRAPHICSITEM_TYPE


class _ResizeHandle(shared.Handle):
    def __init__(self, parent, color):
        super().__init__(parent, color)
        self.hide()

    def mouseReleaseEvent(self, event):
        self.parentItem()._done_resizing()

    def mouseMoveEvent(self, event):
        self.parentItem()._handle_moved(self.mapToParent(event.pos()), self)


