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

import itertools
from PyQt5 import Qt

from .. import shared_resources

"""
Example 1: Simple ROI drawing
    roi = RectROI(rw)
    # click to draw ROI in GUI
    x1, y1, x2, y2 = roi.bounds
    roi.remove_from_rw()

Example 2: Pre-set bounds with a specified aspect ratio (width/height):
    roi = EllipseROI(rw, aspect=2, bounds=(200, 400, 600, 500))
"""

class _ROIMixin:
    def __init__(self, ris_widget, color=Qt.Qt.green, aspect=None, bounds=None):
        """Class for drawing a Region of Interest on a ris_widget.

        The ROI can be drawn by clicking on the upper-left of the desired region,
        then dragging. A second click sets the lower-right. Pressing escape
        before this allows selection of a new upper-left point.

        Afterward, the ROI can be clicked to highlight it, allowing movement or
        resizing. Pressing delete/backspace will remove a selected ROI and allow
        it to be re-drawn.

        The bounds property can be used to obtain the (x1, y1, x2, y2) positions
        of the corners of the ROI. If no ROI is shown, this will be None.

        After use, call remove_from_rw().

        Parameters:
            ris_widget: a ris_widget instance to draw an ROI on
            color: a Qt color for the ROI
            aspect: width/height ratio to maintain, or None
            bounds: (x1, y1, x2, y2) coordinates of corners. If None, the ROI
                can be drawn by clicking on the ris_widget.
        """
        layer_stack = ris_widget.image_scene.layer_stack_item
        super().__init__(layer_stack)
        self.aspect = aspect
        self.display_pen = Qt.QPen(color)
        self.display_pen.setWidth(2)
        self.display_pen.setCosmetic(True)
        self.setPen(self.display_pen)
        self.selected_pen = Qt.QPen(self.display_pen)
        self.selected_pen.setColor(Qt.Qt.red)
        self.dragging = False
        self.rw = ris_widget
        ris_widget.image_view.mouse_release.connect(self._view_mouse_release)
        layer_stack.installSceneEventFilter(self)
        self.resizers = {_ResizeHandle(self, Qt.Qt.red): coords for coords in [
            (0, 0),
            (0.5, 0),
            (1, 0),
            (1, 0.5),
            (1, 1),
            (0.5, 1),
            (0, 1),
            (0, 0.5)
        ]}
        self.bounds = bounds

    @property
    def bounds(self):
        if self.isVisible():
            return self.rect().normalized().getCoords()
        else:
            return None

    @bounds.setter
    def bounds(self, bounds=None):
        if bounds is None:
            self.hide()
        else:
            x1, y1, x2, y2 = bounds
            w = x2 - x1
            if self.aspect is None:
                h = y2 - y1
            else:
                h = w / self.aspect
            self.setRect(x1, y1, w, h)
            self._set_selectable(True)

    def remove_from_rw(self):
        for resizer in self.resizers:
            resizer.remove()
        self.rw.image_view.mouse_release.disconnect(self._view_mouse_release)
        scene = self.rw.image_scene
        scene.removeItem(self)
        scene.layer_stack_item.removeSceneEventFilter(self)

    def shape(self):
        s = Qt.QPainterPathStroker()
        s.setWidth(10/self.scene().views()[0].zoom)
        return s.createStroke(super().shape())

    def boundingRect(self):
        return self.shape().boundingRect()

    def paint(self, painter, option, widget):
        option = Qt.QStyleOptionGraphicsItem(option)
        option.state &= ~Qt.QStyle.State_Selected
        super().paint(painter, option, widget)

    def _view_mouse_release(self, pos):
        if not self.isVisible():
            # no current ROI shown: start a new one
            self.dragging = True
            self.setRect(Qt.QRectF(pos, pos))
            self._set_selectable(False)
            self.show()
        elif self.dragging:
            # finish drawing the roi_rect
            self.dragging = False
            self._set_selectable(True)
            self._done_resizing()

    def _done_resizing(self):
        self.setRect(self.rect().normalized())
        if self.isSelected():
            self._locate_resizers()

    def sceneEventFilter(self, watched, event):
        if self.dragging and event.type() == Qt.QEvent.GraphicsSceneHoverMove:
            self._resize(event.pos())
            return True
        elif event.type() == Qt.QEvent.KeyPress:
            key = event.key()
            if key == Qt.Qt.Key_Escape and self.dragging:
                self.dragging = False
                self.hide()
                return True
            elif key in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace} and self.isSelected():
                self.hide()
                return True
        return False

    def _resize(self, pos):
        rect = Qt.QRectF(self.rect().topLeft(), pos)
        if self.aspect is not None:
            desired_height = rect.width() / self.aspect
            rect.setHeight(desired_height)
        self.setRect(rect)
        if self.isSelected():
            self._locate_resizers()

    def itemChange(self, change, value):
        if change == Qt.QGraphicsItem.ItemSelectedHasChanged:
            if value:
                self.setPen(self.selected_pen)
                self._locate_resizers()
                for resizer in self.resizers:
                    resizer.show()
            else:
                self.setPen(self.display_pen)
                for resizer in self.resizers:
                    resizer.hide()
        return value

    def mouseMoveEvent(self, event):
        delta = event.pos() - event.lastPos()
        self.setRect(self.rect().translated(delta.x(), delta.y()))
        self._locate_resizers()

    def _set_selectable(self, selectable):
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable, selectable)
        self.setSelected(False)

    def _locate_resizers(self):
        rect = self.rect()
        ul = rect.topLeft()
        vector = rect.bottomRight() - ul
        for resizer, coords in self.resizers.items():
            x = ul.x() + vector.x() * coords[0]
            y = ul.y() + vector.y() * coords[1]
            resizer.setPos(x, y)

    def _adjust(self, pos, resizer):
        xc, yc = self.resizers[resizer]
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
        self._locate_resizers()

class RectROI(_ROIMixin, Qt.QGraphicsRectItem):
    QGRAPHICSITEM_TYPE = shared_resources.UNIQUE_QGRAPHICSITEM_TYPE()

    def type(self):
        return self.QGRAPHICSITEM_TYPE

class EllipseROI(_ROIMixin, Qt.QGraphicsEllipseItem):
    QGRAPHICSITEM_TYPE = shared_resources.UNIQUE_QGRAPHICSITEM_TYPE()

    def type(self):
        return self.QGRAPHICSITEM_TYPE

class _ResizeHandle(Qt.QGraphicsRectItem):
    def __init__(self, parent, color):
        super().__init__(-3, -3, 6, 6, parent)
        view = self.scene().views()[0]
        self._zoom_changed(view.zoom)
        view.zoom_changed.connect(self._zoom_changed)
        self.hide()
        self.setPen(Qt.QPen(Qt.Qt.NoPen))
        self.setBrush(Qt.QBrush(color))
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable)

    def remove(self):
        self.scene().views()[0].zoom_changed.disconnect(self._zoom_changed)

    def _zoom_changed(self, z):
        self.setScale(1/z)

    def mouseReleaseEvent(self, event):
        self.parentItem()._done_resizing()

    def mouseMoveEvent(self, event):
        self.parentItem()._adjust(self.mapToParent(event.pos()), self)


