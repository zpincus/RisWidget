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

from contextlib import ExitStack
from .shared_resources import GL, UNIQUE_QGRAPHICSITEM_TYPE
import math
import numpy
from PyQt5 import Qt
from .shader_scene import ShaderItem, ShaderScene, ShaderTexture
import sys

class ItemProp:
    def __init__(self, item_props_list, item_props, name, name_in_label=None, channel_name=None):
        self.name = name
        self.name_in_label = name_in_label
        self.full_name_in_label = name if name_in_label is None else name_in_label
        self.full_name = name
        self.channel_name = channel_name
        if channel_name is not None:
            suffix = '_' + channel_name
            self.full_name += suffix
            self.full_name_in_label += suffix
        item_props[self.full_name] = self
        item_props_list.append(self)
        self.scene_items = {}

    def instantiate(self, histogram_scene):
        scene_item = self._make_scene_item(histogram_scene)
        self.scene_items[histogram_scene] = scene_item
        scene_item.value_changed.connect(histogram_scene.gamma_or_min_max_changed)

    def _make_scene_item(self, histogram_scene):
        raise NotImplementedError()

    def __get__(self, histogram_scene, objtype=None):
        if histogram_scene is None:
            return self
        return self.scene_items[histogram_scene].value

    def __set__(self, histogram_scene, value):
        if histogram_scene is None:
            raise AttributeError("Can't set instance attribute of class.")
        self.scene_items[histogram_scene].value = value

    def __delete__(self, histogram_scene):
        if histogram_scene is None:
            raise AttributeError("Can't delete instance attribute of class.")
        del self.scene_items[histogram_scene].value

class MinMaxItemProp(ItemProp):
    def __init__(self, item_props_list, item_props, min_max_item_props, name, name_in_label=None, channel_name=None):
        super().__init__(item_props_list, item_props, name, name_in_label, channel_name)
        min_max_item_props[self.full_name] = self

    def _make_scene_item(self, histogram_scene):
        return MinMaxItem(histogram_scene.histogram_item, self)

class GammaItemProp(ItemProp):
    def __init__(self, item_props_list, item_props, gamma_item_props, name, name_in_label=None, channel_name=None):
        super().__init__(item_props_list, item_props, name, name_in_label, channel_name)
        gamma_item_props[self.full_name] = self

    def instantiate(self, histogram_scene):
        super().instantiate(histogram_scene)
        scene_item = histogram_scene.get_prop_item(self.full_name)
        scene_item.min_item = histogram_scene.get_prop_item('min' + ('' if self.channel_name is None else '_{}'.format(self.channel_name)))
        scene_item.min_item.value_changed.connect(scene_item.on_min_max_moved)
        scene_item.max_item = histogram_scene.get_prop_item('max' + ('' if self.channel_name is None else '_{}'.format(self.channel_name)))
        scene_item.max_item.value_changed.connect(scene_item.on_min_max_moved)

    def _make_scene_item(self, histogram_scene):
        return GammaItem(histogram_scene.histogram_item, self)

class HistogramScene(ShaderScene):
    gamma_or_min_max_changed = Qt.pyqtSignal()

    item_props_list = []
    item_props = {}
    min_max_item_props = {}
    gamma_item_props = {}

    max = MinMaxItemProp(item_props_list, item_props, min_max_item_props, 'max')
    min = MinMaxItemProp(item_props_list, item_props, min_max_item_props, 'min')
    gamma = GammaItemProp(item_props_list, item_props, gamma_item_props, 'gamma', '\u03b3')

    def __init__(self, parent):
        super().__init__(parent)
        self.setSceneRect(0, 0, 1, 1)
        self.histogram_item = HistogramItem()
        self.addItem(self.histogram_item)
        for item_prop in self.item_props_list:
            item_prop.instantiate(self)
        self.gamma_gamma = 1.0
        self.gamma_red = self.gamma_green = self.gamma_blue = 1.0
        self.min_red = self.min_green = self.min_blue = 0.0
        self.max_red = self.max_green = self.max_blue = 255.0
        self.rescale_enabled = True
        self.min = 0
        self.max = 1
        self.gamma = 1
        self._channel_controls_visible = False
        self.auto_min_max_enabled_action = Qt.QAction('Auto Min/Max', self)
        self.auto_min_max_enabled_action.setCheckable(True)
        self.auto_min_max_enabled_action.setChecked(True)
        self.auto_min_max_enabled_action.toggled.connect(self.on_auto_min_max_enabled_action_toggled)
        self._keep_auto_min_max_on_min_max_value_change = False
        for full_name in HistogramScene.min_max_item_props.keys():
            self.get_prop_item(full_name).value_changed.connect(self.on_auto_min_max_change)

    def on_image_changing(self, image):
        self.histogram_item.on_image_changing(image)
        if self.auto_min_max_enabled:
            self.do_auto_min_max()

    def get_prop_item(self, full_name):
        return HistogramScene.item_props[full_name].scene_items[self]

    def on_auto_min_max_enabled_action_toggled(self, auto_min_max_enabled):
        if self.auto_min_max_enabled:
            self.do_auto_min_max()

    def do_auto_min_max(self):
        image = self.histogram_item.image
        if image is not None:
            self._keep_auto_min_max_on_min_max_value_change = True
            try:
                if image.is_grayscale:
                    self.min, self.max = image.min_max
                else:
                    pass
#                   for channel_name, channel_min_max in zip(image.min_max, ('red','green','blue')):
#                       setattr(self, 'min_'+channel_name, channel_min_max[0])
#                       setattr(self, 'max_'+channel_name, channel_min_max[1])
            finally:
                self._keep_auto_min_max_on_min_max_value_change = False

    def on_auto_min_max_change(self):
        if not self._keep_auto_min_max_on_min_max_value_change and self.auto_min_max_enabled:
            self.auto_min_max_enabled_action.setChecked(False)

    @property
    def auto_min_max_enabled(self):
        return self.auto_min_max_enabled_action.isChecked()

    @auto_min_max_enabled.setter
    def auto_min_max_enabled(self, auto_min_max_enabled):
        self.auto_min_max_enabled_action.setChecked(auto_min_max_enabled)

class HistogramItem(ShaderItem):
    QGRAPHICSITEM_TYPE = UNIQUE_QGRAPHICSITEM_TYPE()

    def __init__(self, graphics_item_parent=None):
        super().__init__(graphics_item_parent)
        self.image = None
        self._image_id = 0
        self._bounding_rect = Qt.QRectF(0, 0, 1, 1)
        self.tex = None

    def type(self):
        return HistogramItem.QGRAPHICSITEM_TYPE

    def boundingRect(self):
        return self._bounding_rect

    def paint(self, qpainter, option, widget):
        if widget is None:
            print('WARNING: histogram_view.HistogramItem.paint called with widget=None.  Ensure that view caching is disabled.')
        elif self.image is None:
            if self.tex is not None:
                self.tex.destroy()
                self.tex = None
        else:
            image = self.image
            view = widget.view
            scene = self.scene()
            if not image.is_grayscale:
                return
                # personal time todo: per-channel RGB histogram support
            with ExitStack() as stack:
                qpainter.beginNativePainting()
                stack.callback(qpainter.endNativePainting)
                gl = GL()
                desired_shader_type = 'g' if image.type in ('g', 'ga') else 'rgb'
                if desired_shader_type in self.progs:
                    prog = self.progs[desired_shader_type]
                else:
                    prog = self.build_shader_prog(desired_shader_type,
                                                  'histogram_widget_vertex_shader.glsl',
                                                  'histogram_widget_fragment_shader_{}.glsl'.format(desired_shader_type))
                desired_tex_width = image.histogram.shape[-1]
                tex = self.tex
                if tex is not None:
                    if tex.width != desired_tex_width:
                        tex.destroy()
                        tex = self.tex = None
                if tex is None:
                    tex = ShaderTexture(gl.GL_TEXTURE_1D)
                    tex.bind()
                    stack.callback(tex.release)
                    gl.glTexParameteri(gl.GL_TEXTURE_1D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
                    gl.glTexParameteri(gl.GL_TEXTURE_1D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
                    # tex stores histogram bin counts - values that are intended to be addressed by element without
                    # interpolation.  Thus, nearest neighbor for texture filtering.
                    gl.glTexParameteri(gl.GL_TEXTURE_1D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
                    gl.glTexParameteri(gl.GL_TEXTURE_1D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
                    tex.image_id = -1
                else:
                    tex.bind()
                    stack.callback(tex.release)
                if image.is_grayscale:
                    if image.type == 'g':
                        histogram = image.histogram
                        max_bin_val = histogram[image.max_histogram_bin]
                    else:
                        histogram = image.histogram[0]
                        max_bin_val = histogram[image.max_histogram_bin[0]]
                    if tex.image_id != self._image_id:
                        orig_unpack_alignment = gl.glGetIntegerv(gl.GL_UNPACK_ALIGNMENT)
                        if orig_unpack_alignment != 1:
                            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
                            # QPainter font rendering for OpenGL surfaces will become broken if we do not restore GL_UNPACK_ALIGNMENT
                            # to whatever QPainter had it set to (when it prepared the OpenGL context for our use as a result of
                            # qpainter.beginNativePainting()).
                            stack.callback(lambda oua=orig_unpack_alignment: gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, oua))
                        gl.glTexImage1D(gl.GL_TEXTURE_1D, 0,
                                        gl.GL_LUMINANCE32UI_EXT, desired_tex_width, 0,
                                        gl.GL_LUMINANCE_INTEGER_EXT, gl.GL_UNSIGNED_INT,
                                        histogram.data)
                        tex.image_id = self._image_id
                        tex.width = desired_tex_width
                        self.tex = tex
                    view.quad_buffer.bind()
                    stack.callback(view.quad_buffer.release)
                    view.quad_vao.bind()
                    stack.callback(view.quad_vao.release)
                    prog.bind()
                    stack.callback(prog.release)
                    vert_coord_loc = prog.attributeLocation('vert_coord')
                    prog.enableAttributeArray(vert_coord_loc)
                    prog.setAttributeBuffer(vert_coord_loc, gl.GL_FLOAT, 0, 2, 0)
                    prog.setUniformValue('tex', 0)
                    prog.setUniformValue('inv_view_size', 1/widget.size().width(), 1/widget.size().height())
                    inv_max_transformed_bin_val = max_bin_val**-scene.gamma_gamma
                    prog.setUniformValue('inv_max_transformed_bin_val', inv_max_transformed_bin_val)
                    prog.setUniformValue('gamma_gamma', scene.gamma_gamma)
                    prog.setUniformValue('rescale_enabled', scene.rescale_enabled)
                    if scene.rescale_enabled:
                        prog.setUniformValue('gamma', scene.gamma)
                        min_max = numpy.array((scene.min, scene.max), dtype=float)
                        self._normalize_min_max(min_max)
                        prog.setUniformValue('intensity_rescale_min', min_max[0])
                        prog.setUniformValue('intensity_rescale_range', min_max[1] - min_max[0])
                    gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
                    gl.glDrawArrays(gl.GL_TRIANGLE_FAN, 0, 4)
                else:
                    pass
                    # personal time todo: per-channel RGB histogram support

    def hoverMoveEvent(self, event):
        image = self.image
        if image is not None:
            x = event.pos().x()
            if x >= 0 and x <= 1:
                if image.is_grayscale:
                    image_type = image.type
                    histogram = image.histogram
                    range_ = image.range
                    bin_count = histogram.shape[-1]
                    bin = int(x * bin_count)
                    bin_width = (range_[1] - range_[0]) / bin_count
                    if image.dtype == numpy.float32:
                        mst = '[{},{}) '.format(range_[0] + bin*bin_width, range_[0] + (bin+1)*bin_width)
                    else:
                        mst = '[{},{}] '.format(math.ceil(bin*bin_width), math.floor((bin+1)*bin_width))
                    vt = '(' + ' '.join((c + ':{}' for c in image_type)) + ')'
                    if len(image_type) == 1:
                        vt = vt.format(histogram[bin])
                    else:
                        vt = vt.format(*histogram[:,bin])
                    self.scene().update_contextual_info(mst + vt, False, self)
                else:
                    pass
                    # personal time todo: per-channel RGB histogram support

    def hoverLeaveEvent(self, event):
        self.scene().clear_contextual_info(self)

    def on_image_changing(self, image):
        super().on_image_changing(image)

class PropItem(Qt.QGraphicsObject):
    value_changed = Qt.pyqtSignal(HistogramScene, float)

    def __init__(self, histogram_item, prop):
        super().__init__(histogram_item)
        self.prop = prop
        self._bounding_rect = Qt.QRectF()

    def boundingRect(self):
        return self._bounding_rect

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.scene().clear_contextual_info(self)

class MinMaxItem(PropItem):
    QGRAPHICSITEM_TYPE = UNIQUE_QGRAPHICSITEM_TYPE()

    def __init__(self, histogram_item, prop):
        super().__init__(histogram_item, prop)
        self._bounding_rect = Qt.QRectF(-0.1, 0, .2, 1)
        self._opposite_item = None
        self.arrow_item = MinMaxArrowItem(self, histogram_item)

    def type(self):
        return MinMaxItem.QGRAPHICSITEM_TYPE

    def paint(self, qpainter, option, widget):
        c = Qt.QColor(Qt.Qt.red)
        c.setAlphaF(0.5)
        pen = Qt.QPen(c)
        pen.setWidth(0)
        qpainter.setPen(pen)
        br = self.boundingRect()
        x = (br.left() + br.right()) / 2
        qpainter.drawLine(x, br.top(), x, br.bottom())

    @property
    def x_to_value(self):
        scene = self.scene()
        if scene is None or scene.histogram_item.image is None:
            def _x_to_value(x):
                return x
        else:
            image = scene.histogram_item.image
            range_ = image.range
            range_width = range_[1] - range_[0]
            if image.dtype == numpy.float32:
                def _x_to_value(x):
                    return range_[0] + x*range_width
            else:
                def _x_to_value(x):
                    return range_[0] + int(x*range_width)
        return _x_to_value

    @property
    def value_to_x(self):
        offset = 0; range_width = 1
        scene = self.scene()
        if scene is not None:
            image = scene.histogram_item.image
            if image is not None:
                range_ = image.range
                offset = range_[0]
                range_width = range_[1] - range_[0]
        def _value_to_x(value):
            return (value - offset) / range_width
        return _value_to_x

    @property
    def value(self):
        return self.x_to_value(self.x())

    @value.setter
    def value(self, value):
        value_to_x = self.value_to_x
        x = value_to_x(value)
        if x < 0 or x > 1:
            x_to_value = self.x_to_value
            raise ValueError('MinMaxItem.value must be in the range [{}, {}].'.format(x_to_value(0), x_to_value(1)))
        if x != self.x():
            self.setX(x)
            self.value_changed.emit(self.scene(), value)
            oitem = self.opposite_item
            ovalue = oitem.value
            if self.prop.name == 'max' and value < ovalue or \
               self.prop.name == 'min' and value > ovalue:
                oitem.value = value

    @value.deleter
    def value(self):
        image = self.scene().histogram_item.image
        if image is None:
            range_ = (0, 1)
        else:
            range_ = image.range
        self.value = range_[self.prop.name == 'max']

    @property
    def opposite_item(self):
        if self._opposite_item is None:
            oname = 'max' if self.prop.name == 'min' else 'min'
            if self.prop.channel_name is not None:
                oname += '_' + self.prop.channel_name
            self._opposite_item = self.scene().get_prop_item(oname)
        return self._opposite_item

class MinMaxArrowItem(Qt.QGraphicsObject):
    QGRAPHICSITEM_TYPE = UNIQUE_QGRAPHICSITEM_TYPE()

    def __init__(self, min_max_item, histogram_item):
        super().__init__(histogram_item)
        self._path = Qt.QPainterPath()
        self.min_max_item = min_max_item
        if min_max_item.prop.name == 'min':
            polygonf = Qt.QPolygonF((Qt.QPointF(0.5, -10), Qt.QPointF(6, 0), Qt.QPointF(0.5, 10)))
        else:
            polygonf = Qt.QPolygonF((Qt.QPointF(-0.5, -10), Qt.QPointF(-6, 0), Qt.QPointF(-0.5, 10)))
        self._path.addPolygon(polygonf)
        self._path.closeSubpath()
        self._bounding_rect = self._path.boundingRect()
        self.pen = Qt.QPen(Qt.QColor(Qt.Qt.transparent))
        color = Qt.QColor(Qt.Qt.red)
        color.setAlphaF(0.5)
        self.brush = Qt.QBrush(color)
        self.setFlag(Qt.QGraphicsItem.ItemIgnoresTransformations)
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable)
        # GUI behavior is much more predictable with min/max arrow item selectability disabled:
        # with ItemIsSelectable enabled, min/max items can exhibit some very unexpected behaviors, as we
        # do not do anything differently in our paint function if the item is selected vs not, making
        # it unlikely one would realize one or more items are selected.  If multiple items are selected,
        # they will move together when one is dragged.  Additionally, arrow key presses would move
        # selected items if their viewport has focus (viewport focus is also not indicated).
        # Items are non-selectable by default; the following line is present only to make intent clear.
        #self.setFlag(Qt.QGraphicsItem.ItemIsSelectable, False)
        self._ignore_x_change = False
        self.setPos(min_max_item.x(), 0.5)
        self.xChanged.connect(self.on_x_changed)
        self.yChanged.connect(self.on_y_changed)
        min_max_item.value_changed.connect(self.on_min_max_value_changed)

    def type(self):
        return MinMaxArrowItem.QGRAPHICSITEM_TYPE

    def boundingRect(self):
        return self._bounding_rect

    def shape(self):
        return self._path

    def paint(self, qpainter, option, widget):
        qpainter.setPen(self.pen)
        qpainter.setBrush(self.brush)
        qpainter.drawPath(self._path)

    def on_x_changed(self):
        x = self.x()
        if x < 0:
            self.setX(0)
        elif x > 1:
            self.setX(1)
        self.min_max_item.value = self.min_max_item.x_to_value(x)

    def on_y_changed(self):
        if self.y() != 0.5:
            self.setY(0.5)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.scene().update_contextual_info('{}: {}'.format(self.min_max_item.prop.full_name_in_label, self.min_max_item.value), False, self)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.scene().update_contextual_info('{}: {}'.format(self.min_max_item.prop.full_name_in_label, self.min_max_item.value), False, self)

    def on_min_max_value_changed(self):
        desired_x = self.min_max_item.x()
        if self.x() != desired_x:
            self.setX(desired_x)

class GammaItem(PropItem):
    QGRAPHICSITEM_TYPE = UNIQUE_QGRAPHICSITEM_TYPE()
    RANGE = (0.0625, 16.0)
    CURVE_VERTEX_COUNT = 62
    CURVE_VERTEX_COMPUTE_POSITIONS = numpy.linspace(0, 1, num=CURVE_VERTEX_COUNT, endpoint=True)[1:-1]

    def __init__(self, histogram_item, prop):
        super().__init__(histogram_item, prop)
        self._bounding_rect = Qt.QRectF(0, 0, 1, 1)
        self._value = None
        self._path = Qt.QPainterPath()
        self.setFlag(Qt.QGraphicsItem.ItemIsMovable)
        self.setZValue(-1)
        # This is a convenient way to ensure that only primary mouse button clicks cause
        # invocation of mouseMoveEvent(..).  Without this, it would be necessary to
        # override mousePressEvent(..) and check which buttons are down, in addition to
        # checking which buttons remain down in mouseMoveEvent(..).
        self.setAcceptedMouseButtons(Qt.Qt.LeftButton)

    def type(self):
        return GammaItem.QGRAPHICSITEM_TYPE

    def shape(self):
        pen = Qt.QPen()
        pen.setWidthF(0)
        stroker = Qt.QPainterPathStroker(pen)
        stroker.setWidth(0.2)
        return stroker.createStroke(self._path)

    def paint(self, qpainter, option, widget):
        if not self._path.isEmpty():
            c = Qt.QColor(Qt.Qt.yellow)
            c.setAlphaF(0.5)
            pen = Qt.QPen(c)
            pen.setWidth(0)
            qpainter.setPen(pen)
            qpainter.setBrush(Qt.QColor(Qt.Qt.transparent))
            qpainter.drawPath(self._path)

    def on_min_max_moved(self):
        min_x = self.min_item.x()
        max_x = self.max_item.x()
        t = Qt.QTransform()
        t.translate(min_x, 0)
        t.scale(max_x - min_x, 1)
        self.setTransform(t)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.scene().update_contextual_info('{}: {}'.format(self.prop.full_name_in_label, self.value), False, self)

    def mouseMoveEvent(self, event):
        current_x, current_y = map(lambda v: min(max(v, 0.001), 0.999),
                                   (event.pos().x(), event.pos().y()))
        current_y = 1-current_y
        self.value = min(max(math.log(current_y, current_x), GammaItem.RANGE[0]), GammaItem.RANGE[1])
        self.scene().update_contextual_info('{}: {}'.format(self.prop.full_name_in_label, self.value), False, self)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if value < GammaItem.RANGE[0] or value > GammaItem.RANGE[1]:
            raise ValueError('GammaItem.value must be in the range [{}, {}].'.format(GammaItem.RANGE[0], GammaItem.RANGE[1]))
        if value != self._value:
            self.prepareGeometryChange()
            self._value = float(value)
            self._path = Qt.QPainterPath(Qt.QPointF(0, 1))
            for x, y in zip(GammaItem.CURVE_VERTEX_COMPUTE_POSITIONS, GammaItem.CURVE_VERTEX_COMPUTE_POSITIONS**self._value):
                self._path.lineTo(x, 1.0-y)
            self._path.lineTo(1, 0)
            self.update()
            self.value_changed.emit(self.scene(), self._value)

    @value.deleter
    def value(self):
        self.value = 1
