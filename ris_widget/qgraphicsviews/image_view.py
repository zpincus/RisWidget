# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
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
# Authors: Erik Hvatum <ice.rikh@gmail.com>

import numpy
import math
from PyQt5 import Qt

from . import base_view

class ImageView(base_view.BaseView):
    # mouse wheel up/down changes the zoom among values of 2**(i*ZOOM_EXPONENT) where i is an integer
    ZOOM_EXPONENT = 0.125
    zoom_changed = Qt.pyqtSignal(float)
    # mouse_release: signal emitted after a mouse-release event (that doesn't end a drag to scroll the image)
    # The signal contains the position of the mouse, in image coordinates
    mouse_release = Qt.pyqtSignal(Qt.QPointF)

    def __init__(self, scene, parent):
        super().__init__(scene, parent)
        self.setMinimumSize(Qt.QSize(100,100))
        self._zoom = 1
        self.zoom_to_fit_action = Qt.QAction('Zoom to Fit', self)
        self.zoom_to_fit_action.setCheckable(True)
        self.zoom_to_fit_action.setChecked(True)
        self._ignore_zoom_to_fit_action_toggle = False
        self.zoom_to_fit_action.toggled.connect(self.on_zoom_to_fit_action_toggled)
        self.zoom_changed.connect(self._on_zoom_changed)
        # Calling self.setDragMode(Qt.QGraphicsView.ScrollHandDrag) would enable QGraphicsView's built-in
        # click-drag panning, saving us from having to implement it.  However, QGraphicsView is very
        # insistent about setting the mouse cursor to the hand icon in ScrollHandDragMode.  It does this
        # in a number of places that would have to be invidually overridden, making it much simpler to
        # implement click-drag panning ourselves.
        self.setDragMode(Qt.QGraphicsView.NoDrag)
        self.panning = False
        self.setAcceptDrops(True)
        self.background_color = .5, .5, .5

    def _on_layer_stack_item_bounding_rect_changed(self):
        if self.zoom_to_fit:
            self._apply_zoom()

    def _on_resize(self, size):
        if self.zoom_to_fit:
            self._apply_zoom()

    def _on_zoom_changed(self, zoom):
        self.scene().fill_viewport(self)

    def mousePressEvent(self, event):
        # For our convenience, Qt sets event accepted to true before calling us, so that we don't have to in the common case
        # where a handler handles the event and the event should be considered handled. (Some unhandled events propagate
        # to parent widgets, so this can be important)
        event.setAccepted(False)
        # Now call the superclass handler, which will ask items in the graphics scene if they wanted the event.
        super().mousePressEvent(event)
        if event.isAccepted():
            return
        # If the mouse click landed on an interactive scene item, super().mousePressEvent(event) would have set
        # event to accepted. So, neither the view nor the scene wanted this mouse click. It may thus be a
        # drag-pan initiation event:
        if event.button() == Qt.Qt.LeftButton:
            # It is, and we're handling this event
            self._panning_prev_mouse_pos = event.pos()
            self.panning = 'clicked'
            event.setAccepted(True)

    def mouseReleaseEvent(self, event):
        event.setAccepted(False)
        super().mouseReleaseEvent(event)
        if event.isAccepted():
            return
        if event.button() == Qt.Qt.LeftButton:
            if self.panning:
                if self.panning != 'dragging':
                    # if this release doesn't terminate a panning drag, then emit
                    # a mouse-release signal for those interested.
                    self.mouse_release.emit(self.mapToScene(event.pos()))
                event.setAccepted(True)
                self.panning = False

    def mouseMoveEvent(self, event):
        event.setAccepted(False)
        super().mouseMoveEvent(event)
        if event.isAccepted():
            return
        # Note: we will receive mouse move events even in the case that a QGraphicsItem
        # is being dragged. While a QGraphicsItem that is clicked on will accept the click,
        # so that we can distinguish between a click on an item and a click on the scene
        # itself, for some reason QGraphicsItems that are dragged do not accept the
        # mouseMoveEvent (indeed, the docs state that these events can't be accepted
        # by QGraphicsItems...)
        # So instead, we need to see if this View had previously accepted a pan-starting
        # mouse click, or if it did not receive the click that initiated this drag.
        if self.panning and event.buttons() & Qt.Qt.LeftButton:
            self.panning = 'dragging'
            # This block more or less borrowed from QGraphicsView::mouseMoveEvent(QMouseEvent *event), found in
            # qtbase/src/widgets/graphicsview/qgraphicsview.cpp
            hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
            pos = event.pos()
            delta = pos - self._panning_prev_mouse_pos
            hbar.setValue(hbar.value() - (delta.x() if self.isLeftToRight() else -delta.x()))
            vbar.setValue(vbar.value() - delta.y())
            self._panning_prev_mouse_pos = pos

    def dragEnterEvent(self, event):
        event.setAccepted(False)
        self.parent().dragEnterEvent(event)
        if not event.isAccepted():
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        event.setAccepted(False)
        self.parent().dragMoveEvent(event)
        if not event.isAccepted():
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        event.setAccepted(False)
        self.parent().dropEvent(event)
        if not event.isAccepted():
            super().dropEvent(event)

    def wheelEvent(self, event):
        wheel_delta = event.angleDelta().y()
        if wheel_delta == 0:
            return
        zoom_in = wheel_delta > 0

        # mouse wheel up/down changes the zoom among values of 2**(i*ZOOM_EXPONENT) where i is an integer
        # first, figure out what the current i value is (may be non-integer if custom zoom was set)
        exponent_multiplier = math.log2(self._zoom)/self.ZOOM_EXPONENT
        int_multiplier = round(exponent_multiplier)
        if abs(int_multiplier - exponent_multiplier) < 0.01:
            exponent_multiplier = int_multiplier
        elif zoom_in:
            # reset to zoom stop just less-zoomed-in than the current zoom
            exponent_multiplier = math.floor(exponent_multiplier)
        else: # zooming out
            # reset to zoom stop just more-zoomed-in than the current zoom
            exponent_multiplier = math.ceil(exponent_multiplier)
        if zoom_in:
            exponent_multiplier += 1
        else:
            exponent_multiplier -= 1
        current_zoom = self._zoom
        self._zoom = 2**(exponent_multiplier*self.ZOOM_EXPONENT)

        scale_zoom = self._zoom / current_zoom
        self.setTransformationAnchor(Qt.QGraphicsView.AnchorUnderMouse)
        self.scale(scale_zoom, scale_zoom)
        self.setTransformationAnchor(Qt.QGraphicsView.AnchorViewCenter)
        if self.zoom_to_fit:
            self._ignore_zoom_to_fit_action_toggle = True
            self.zoom_to_fit_action.setChecked(False)
            self._ignore_zoom_to_fit_action_toggle = False
        self.zoom_changed.emit(self._zoom)

    def on_zoom_to_fit_action_toggled(self):
        if not self._ignore_zoom_to_fit_action_toggle:
            if not self.zoom_to_fit:
                # unchecking zoom to fit: return to 100%
                self._zoom = 1
            self._apply_zoom()

    @property
    def zoom_to_fit(self):
        return self.zoom_to_fit_action.isChecked()

    @zoom_to_fit.setter
    def zoom_to_fit(self, zoom_to_fit):
        self.zoom_to_fit_action.setChecked(zoom_to_fit)

    @property
    def zoom(self):
        return self._zoom

    @zoom.setter
    def zoom(self, zoom):
        self._zoom = zoom
        if self.zoom_to_fit:
            self._ignore_zoom_to_fit_action_toggle = True
            self.zoom_to_fit_action.setChecked(False)
            self._ignore_zoom_to_fit_action_toggle = False
        self._apply_zoom()

    def _apply_zoom(self):
        if self.zoom_to_fit:
            self.fitInView(self.scene().layer_stack_item, Qt.Qt.KeepAspectRatio)
            current_zoom = self.transform().m22()
            if current_zoom != self._zoom:
                self._zoom = current_zoom
                self.zoom_changed.emit(self._zoom)
        else:
            old_transform = Qt.QTransform(self.transform())
            self.resetTransform()
            self.translate(old_transform.dx(), old_transform.dy())
            self.scale(self._zoom, self._zoom)
            self.zoom_changed.emit(self._zoom)
