# This code is licensed under the MIT License (see LICENSE file for details)

"""
Example 1: Simple ROI drawing
    roi = RectROI(rw)
    # click to draw ROI in GUI
    (x1, y1), (x2, y2) = roi.geometry
    roi.remove()

Example 2: Pre-set bounds with a specified aspect ratio (width/height):
    roi = EllipseROI(rw, aspect=2, geometry=((200, 400), (600, 500)))
"""

from PyQt5 import Qt

from .. import shared_resources
from . import base


class _ROIMixin(base.RWGeometryItemMixin):
    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None, aspect=None):
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
            aspect: width/height ratio to maintain, or None
        """
        self.aspect = aspect
        super().__init__(ris_widget, color, geometry)
        self.dragging = False
        self.handles = {_ResizeHandle(self, self.parentItem(), Qt.Qt.red): coords for coords in [
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
        self._geometry_changed()

    def _aspect_adjusted_rect(self, rect):
        if self.aspect is not None:
            desired_height = rect.width() / self.aspect
            rect.setHeight(desired_height)
        return rect

    def _view_mouse_release(self, pos, modifiers):
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
                # just a resize event: don't call official geometry setter (which calls callbacks, etc) until done with dragging
                rect = self.rect()
                rect.setBottomRight(event.pos())
                self.setRect(self._aspect_adjusted_rect(rect))
                return False # let the rest of the scene see the hover move too (i.e. update the mouseover text)
            elif event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Escape:
                self.geometry = None # this sets dragging false
                return True
        return super().sceneEventFilter(watched, event)

    def _done_resizing(self):
        # Now reset self.geometry to clean up position and call callbacks
        x1, y1, x2, y2 = self.rect().getCoords()
        # NB: call _set_geometry rather than setting .geometry property to keep selected state
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
        # called during handle dragging: don't set .geometry propery directly, since we're not
        # officially done moving. (_done_resizing() is called when that happens)
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
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()


class EllipseROI(_ROIMixin, Qt.QGraphicsEllipseItem):
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()


class _ResizeHandle(base.Handle):
    def __init__(self, parent, layer_stack, color):
        super().__init__(parent, layer_stack, color)
        self.hide()

    def mouseReleaseEvent(self, event):
        self.parentItem()._done_resizing()

    def mouseMoveEvent(self, event):
        self.parentItem()._handle_moved(self.mapToParent(event.pos()), self)
        self.layer_stack.contextual_info_pos = self.pos()
        self.layer_stack._update_contextual_info()


