from PyQt5 import Qt

class RWGeometryItemMixin:
    def __init__(self, ris_widget, color=Qt.Qt.green, geometry=None, on_geometry_change=None):
        """Class for drawing a geometry on a ris_widget.

        To remove from the ris_widget, call remove().

        Subclasses must implement a geometry property that calls on_geometry_change.

        Parameters:
            ris_widget: a ris_widget instance to draw an ROI on
            color: a Qt color for the ROI
            geometry: list of (x,y) coordinate pairs.
            on_geometry_change: callback that will be called with new geometry,
                or None if the geometry is deleted.
        """
        layer_stack = ris_widget.image_scene.layer_stack_item
        self._mouse_connected = False
        super().__init__(layer_stack)
        self.display_pen = Qt.QPen(color)
        self.on_geometry_change = on_geometry_change
        self.display_pen.setWidth(2)
        self.display_pen.setCosmetic(True)
        self.setPen(self.display_pen)
        self.selected_pen = Qt.QPen(self.display_pen)
        self.selected_pen.setColor(Qt.Qt.red)
        self.rw = ris_widget
        self.geometry = geometry

    def remove(self):
        if self._mouse_connected:
            self.rw.image_view.mouse_release.disconnect(self._view_mouse_release)
        self.rw.image_scene.removeItem(self)
        del self.rw

    def shape(self):
        s = Qt.QPainterPathStroker()
        s.setWidth(8/self.scene().views()[0].zoom)
        return s.createStroke(super().shape())

    def boundingRect(self):
        return self.shape().boundingRect()

    def paint(self, painter, option, widget):
        option = Qt.QStyleOptionGraphicsItem(option)
        option.state &= ~Qt.QStyle.State_Selected
        super().paint(painter, option, widget)

    def _view_mouse_release(self, pos):
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


class Handle(Qt.QGraphicsRectItem):
    def __init__(self, parent, color):
        super().__init__(-4, -4, 8, 8)
        # TODO: WTF with PyQt5 v. 5.9 on Linux, core is dumped if the parent
        # is set in the constructor above. (Only if the parent is a subclass
        # of _ROIMixin?!) But parenting later works fine.
        self.setParentItem(parent)
        view = self.scene().views()[0]
        self._zoom_changed(view.zoom)
        view.zoom_changed.connect(self._zoom_changed)
        self.setPen(Qt.QPen(Qt.Qt.NoPen))
        self.setBrush(Qt.QBrush(color))
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable)

    def remove(self):
        self.scene().views()[0].zoom_changed.disconnect(self._zoom_changed)

    def _zoom_changed(self, z):
        self.setScale(1/z)
