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
# Authors: Erik Hvatum <ice.rikh@gmail.com>, Zach Pincus

from PyQt5 import Qt
from .qgraphicsitems import viewport_rect_item
from .qgraphicsitems import contextual_info_item
from .qgraphicsitems import layer_stack_item
from .qgraphicsitems import histogram_items

class BaseScene(Qt.QGraphicsScene):
    """BaseScene provides for creating and maintaining a ContextualInfoItem (or compatible).

    Instances of BaseScene have a .viewport_rect_item attribute, which is an instance of
    ViewportRectItem, an invisible graphics item.  The associated view will call fill_viewport()
    as necessary to ennsure the .viewport_rect_item exactly fills that view's viewport.

    If you wish for a scene element to remain fixed in scale with respect to the viewport and fixed in
    position with respect to the top-left corner of the viewport, simply parent the item in question to
    .viewport_rect_item (contextual_info_item does this, for example).  To make item placement relative
    to a viewport anchor that varies with viewport size, such as the bottom-right corner, it must be
    repositioned in response to emission of the .viewport_rect_item.size_changed signal.

    Although the Qt Graphics View Framework supports multiple views into a single scene, we don't
    have a need for this capability, and we do not go out of our way to make it work correctly (which
    would entail significant additional code complexity)."""

    def __init__(self, parent):
        super().__init__(parent=None)
        self.viewport_rect_item = viewport_rect_item.ViewportRectItem()
        self.addItem(self.viewport_rect_item)
        self.contextual_info_item = contextual_info_item.ContextualInfoItem(self.viewport_rect_item)
        self.contextual_info_item.setPos(10, 5)

    def fill_viewport(self, view):
        self.viewport_rect_item.size = view.size()
        view_origin = view.mapToScene(0,0)
        if self.viewport_rect_item.pos() != view_origin:
            self.viewport_rect_item.setPos(view_origin)


class ImageScene(BaseScene):
    def __init__(self, layer_stack, parent=None):
        super().__init__(parent)
        self.layer_stack_item = layer_stack_item.LayerStackItem(layer_stack=layer_stack)
        self.layer_stack_item.bounding_rect_changed.connect(self._on_layer_stack_item_bounding_rect_changed)
        self.addItem(self.layer_stack_item)

    def _on_layer_stack_item_bounding_rect_changed(self):
        self.setSceneRect(self.layer_stack_item.boundingRect())
        view = self.views()[0] # image scenes have only one view
        self.fill_viewport(view)
        view._on_layer_stack_item_bounding_rect_changed()


class HistogramScene(BaseScene):
    def __init__(self, layer_stack, parent=None):
        super().__init__(parent)
        self.setSceneRect(0, 0, 1, 1)
        self.histogram_item = histogram_items.HistogramItem(layer_stack=layer_stack)
        self.addItem(self.histogram_item)

