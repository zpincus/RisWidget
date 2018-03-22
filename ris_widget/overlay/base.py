# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

from .. import shared_resources

class RWGeometryItemMixin:
    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None):
        """Class for drawing a geometry on a ris_widget.

        To remove from the ris_widget, call remove().

        Subclasses must implement a geometry property that calls _geometry_changed(),
        which takes care of calling geometry-changed callbacks.

        Parameters:
            ris_widget: a ris_widget instance to draw geometry on
            color: a Qt color for the geometry
            geometry: list of (x,y) coordinate pairs.

        Class variables:
            geometry_change_callbacks: list of callbacks that will be called
                when geometry is changed, with the new geometry as the parameter
                or None if the geometry is deleted.
        """
        layer_stack = ris_widget.image_scene.layer_stack_item
        self._mouse_connected = False
        self.display_pen = Qt.QPen(color)
        self.geometry_change_callbacks = []
        self.display_pen.setWidth(2)
        self.display_pen.setCosmetic(True)
        self.selected_pen = Qt.QPen(self.display_pen)
        self.selected_pen.setColor(Qt.Qt.red)
        self.rw = ris_widget
        super().__init__(layer_stack)
        layer_stack.installSceneEventFilter(self)
        self.setPen(self.display_pen)
        self.geometry = geometry

    # all subclasses must define their own unique QGRAPHICSITEM_TYPE
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    def type(self):
        return self.QGRAPHICSITEM_TYPE

    def _geometry_changed(self):
        for callback in self.geometry_change_callbacks:
            callback(self.geometry)

    def remove(self):
        self.parentItem().removeSceneEventFilter(self)
        if self._mouse_connected:
            self.rw.image_view.mouse_release.disconnect(self._view_mouse_release)
        self.rw.image_scene.removeItem(self)
        del self.rw

    def shape(self):
        # make the shape larger than the visible lines to make it easier to click on
        s = Qt.QPainterPathStroker()
        s.setWidth(12/self.scene().views()[0].zoom)
        return s.createStroke(super().shape())

    def boundingRect(self):
        # need to return a bounding rect around the enlarged shape
        return self.shape().boundingRect()

    def paint(self, painter, option, widget):
        option = Qt.QStyleOptionGraphicsItem(option)
        option.state &= ~Qt.QStyle.State_Selected
        super().paint(painter, option, widget)

    def _view_mouse_release(self, pos, modifiers):
        # Called when ROI item is visible, and a mouse-up on the underlying
        # view occurs. (I.e. not on this item itself)
        pass

    def itemChange(self, change, value):
        if change == Qt.QGraphicsItem.ItemSelectedHasChanged:
            if value:
                self._selected()
            else:
                self._deselected()
        elif change == Qt.QGraphicsItem.ItemVisibleHasChanged:
            if value:
                # Usually when the item is constructed we get a "made visible" event first thing,
                # so this is where we'll connect the mouse function.
                self.rw.image_view.mouse_release.connect(self._view_mouse_release)
                self._mouse_connected = True
            elif self._mouse_connected:
                # if the item is constructed and immediately hidden, a visibility change
                # to invisible will be the first change! So there will be no
                # connection made and the disconnect below will be an error unless
                # we make sure only to disconnect after a connect has occured
                self.rw.image_view.mouse_release.disconnect(self._view_mouse_release)
                self._mouse_connected = False
        return value

    def _selected(self):
        self.setPen(self.selected_pen)

    def _deselected(self):
        self.setPen(self.display_pen)

    def sceneEventFilter(self, watched, event):
        if (event.type() == Qt.QEvent.KeyPress and self.isSelected()
              and event.key() in {Qt.Qt.Key_Delete, Qt.Qt.Key_Backspace}):
            self.geometry = None
            return True
        return False


class SceneListener(Qt.QGraphicsItem):
    def __init__(self, ris_widget):
        super().__init__(ris_widget.image_scene.layer_stack_item)
        self.setFlag(Qt.QGraphicsItem.ItemHasNoContents)
        self.parentItem().installSceneEventFilter(self)

    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    def type(self):
        return self.QGRAPHICSITEM_TYPE

    def remove(self):
        self.parentItem().removeSceneEventFilter(self)

    def boundingRect(self):
        return Qt.QRectF()


class Handle(Qt.QGraphicsRectItem):
    RECT = (-3, -3, 6, 6)
    def __init__(self, parent, layer_stack, color):
        super().__init__(*self.RECT)
        # TODO: WTF with PyQt5 v. 5.9 on Linux, core is dumped if the parent
        # is set in the constructor above. (Only if the parent is a subclass
        # of _ROIMixin?!) But parenting later works fine.
        self.setParentItem(parent)
        self.layer_stack = layer_stack
        view = self.scene().views()[0]
        self._zoom_changed(view.zoom)
        view.zoom_changed.connect(self._zoom_changed)
        self.setPen(Qt.QPen(Qt.Qt.NoPen))
        self.setBrush(Qt.QBrush(color))
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable)

    def remove(self):
        scene = self.scene()
        scene.views()[0].zoom_changed.disconnect(self._zoom_changed)
        scene.removeItem(self)

    def _zoom_changed(self, z):
        self.setScale(1/z)

    def shape(self):
        # make the shape larger than the visible rect to make it easier to click on
        path = Qt.QPainterPath()
        path.addRect(self.rect().adjusted(-4, -4, 4, 4))
        return path

    def boundingRect(self):
        # need to return a bounding rect around the enlarged shape
        return self.shape().boundingRect()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.layer_stack.contextual_info_pos = self.pos()
        self.layer_stack._update_contextual_info()


class SelectableHandle(Handle):
    def __init__(self, parent, layer_stack, color):
        super().__init__(parent, layer_stack, color)
        self.display_brush = self.brush() # set in superclass init
        self.selected_brush = Qt.QBrush(Qt.Qt.red)
        self.setFlag(Qt.QGraphicsItem.ItemIsSelectable)

    def itemChange(self, change, value):
        if change == Qt.QGraphicsItem.ItemSelectedHasChanged:
            if value:
                self._selected()
            else:
                self._deselected()
        return value

    def paint(self, painter, option, widget):
        option = Qt.QStyleOptionGraphicsItem(option)
        option.state &= ~Qt.QStyle.State_Selected
        super().paint(painter, option, widget)

    def _selected(self):
        self.setBrush(self.selected_brush)

    def _deselected(self):
        self.setBrush(self.display_brush)
