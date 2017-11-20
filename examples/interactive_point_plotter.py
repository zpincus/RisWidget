# This code is licensed under the MIT License (see LICENSE file for details)

from zplib.image import colorize
import PyQt5.Qt as Qt

class Circle(Qt.QGraphicsEllipseItem):
    def __init__(self, x, y, r, rgba, metadata, parent=None):
        r2 = r/2
        super().__init__(x-r2, y-r2, r, r, parent)
        self.setBrush(Qt.QBrush(Qt.QColor(*rgba)))
        self.setPen(Qt.QPen(Qt.Qt.NoPen))
        self.metadata = metadata

    def mousePressEvent(self, event):
        print(self.metadata)
        event.ignore()

def plot(positions, values, radius, rw):
    colors = colorize.color_map(colorize.scale(values, output_max=1))
    circles = [Circle(x, y, radius, color, metadata=(x, y, value)) for (x, y), color, value in zip(positions, colors, values)]
    for c in circles:
        rw.image_scene.addItem(c)
    return circles

