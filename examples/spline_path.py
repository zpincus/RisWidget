from zplib.curve import interpolate
import PyQt5.Qt as Qt

def plot_spline(rw, points, smoothing, rgba):
    tck = interpolate.fit_spline(points, smoothing=smoothing)
    bezier_elements = interpolate.spline_to_bezier(tck)
    path = Qt.QPainterPath()
    path.moveTo(*bezier_elements[0][0])
    for (sx, sy), (c1x, c1y), (c2x, c2y), (ex, ey) in bezier_elements:
        path.cubicTo(c1x, c1y, c2x, c2y, ex, ey)
    display_path = Qt.QGraphicsPathItem(path, parent=rw.image_scene.layer_stack_item)
    pen = Qt.QPen(Qt.QColor(*rgba))
    pen.setWidth(2)
    pen.setCosmetic(True)
    display_path.setPen(pen)
    return tck, display_path

def remove_spline(rw, display_path):
    rw.image_scene.removeItem(display_path)

