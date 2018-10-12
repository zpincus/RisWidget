from PyQt5 import Qt

def mouse_release(self, pos, modifiers):
    x, y = pos.x(), pos.y() # in image coordinates
    if modifiers & Qt.Qt.AltModifier:
        # do somethind different if alt is pressed?
        pass

# to start getting mouse-release signals
rw.image_view.mouse_release.connect(view_mouse_release)

# to stop getting mouse-release signals
rw.image_view.mouse_release.disconnect(view_mouse_release)

