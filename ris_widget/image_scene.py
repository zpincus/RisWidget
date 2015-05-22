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

#from ._qt_debug import qtransform_to_numpy
from .image import Image
from .shared_resources import GL, UNIQUE_QGRAPHICSITEM_TYPE
from .shader_scene import ShaderScene, ItemWithImage, ShaderItemWithImage
from .shader_view import ShaderView
from contextlib import ExitStack
import math
import numpy
from PyQt5 import Qt
from string import Template
import sys

class ImageScene(ShaderScene):
    def __init__(self, parent, ImageItemClass, ContextualInfoItemClass):
        super().__init__(parent, ContextualInfoItemClass)
        self.image_item = ImageItemClass()
        self.image_item.image_changing.connect(self._on_image_changing)
        self.addItem(self.image_item)

    def _on_image_changing(self, image_item, old_image, new_image):
        assert self.image_item is image_item
        self.setSceneRect(image_item.boundingRect())
        for view in self.views():
            view._on_image_changing()

class ImageItem(ShaderItemWithImage):
    QGRAPHICSITEM_TYPE = UNIQUE_QGRAPHICSITEM_TYPE()
    _OVERLAY_UNIFORMS_TEMPLATE = Template(
"""uniform sampler2D overlay${idx}_tex;
uniform mat3 overlay${idx}_frag_to_tex;
uniform float overlay${idx}_tex_global_alpha;
uniform float overlay${idx}_rescale_min;
uniform float overlay${idx}_rescale_range;
uniform float overlay${idx}_gamma;
""")
    _OVERLAY_BLENDING_TEMPLATE = Template(
"""    tex_coord = transform_frag_to_tex(overlay${idx}_frag_to_tex);
    if(tex_coord.x >= 0 && tex_coord.x < 1 && tex_coord.y >= 0 && tex_coord.y < 1)
    {
        s = texture2D(overlay${idx}_tex, tex_coord);
        s = ${getcolor_expression};
        sa = clamp(s.a, 0, 1) * overlay${idx}_tex_global_alpha;
        sc = min_max_gamma_transform(s.rgb, overlay${idx}_rescale_min, overlay${idx}_rescale_range, overlay${idx}_gamma);
        ${extra_transformation_expression};
        sca = sc * sa;
        ${blend_function}
        da = clamp(da, 0, 1);
        dca = clamp(dca, 0, 1);
    }
""")

    overlay_attaching = Qt.pyqtSignal(ItemWithImage)
    overlay_detaching = Qt.pyqtSignal(ItemWithImage)

    def __init__(self, parent_item=None):
        super().__init__(parent_item)
        self._overlay_items = []
        self._overlay_items_z_sort_is_current = True
        self.setAcceptHoverEvents(True)
        self.trilinear_filtering_enabled_changed.connect(self.update)
        self.getcolor_expression_changed.connect(self.update)
        self.extra_transformation_expression_changed.connect(self.update)
        self.min_changed.connect(self.update)
        self.max_changed.connect(self.update)
        self.gamma_changed.connect(self.update)

    def type(self):
        return ImageItem.QGRAPHICSITEM_TYPE

    def validate_image(self, image):
        if image.num_channels != 1:
            raise ValueError('image_scene.ImageItem supports grayscale (single channel, ie MxN, not MxNxc) images.')

    def paint(self, qpainter, option, widget):
        assert widget is not None, 'image_view.HistogramItem.paint called with widget=None.  Ensure that view caching is disabled.'
        qpainter.beginNativePainting()
        with ExitStack() as estack:
            estack.callback(qpainter.endNativePainting)
            self._update_tex(estack)
            if self._tex is not None and self._getcolor_expression is not None:
                gl = GL()
                image = self._image
                self._update_overlay_items_z_sort()
                prog_desc = [self._getcolor_expression, self._extra_transformation_expression]
                visible_overlays = []
                for overlay_item in self._overlay_items:
                    if overlay_item.isVisible() and overlay_item._image is not None:
                        prog_desc += [overlay_item._getcolor_expression, overlay_item._blend_function, overlay_item._extra_transformation_expression]
                        visible_overlays.append(overlay_item)
                prog_desc = tuple(prog_desc)
                if prog_desc in self.progs:
                    prog = self.progs[prog_desc]
                else:
                    overlay_uniforms = ''
                    do_overlay_blending = ''
                    for overlay_idx, overlay_item in enumerate(visible_overlays):
                        overlay_uniforms += self._OVERLAY_UNIFORMS_TEMPLATE.substitute(idx=overlay_idx)
                        do_overlay_blending += self._OVERLAY_BLENDING_TEMPLATE.substitute(
                            idx=overlay_idx,
                            getcolor_expression=overlay_item._getcolor_expression,
                            extra_transformation_expression='' if overlay_item._extra_transformation_expression is None else overlay_item._extra_transformation_expression,
                            blend_function=overlay_item._blend_function_impl)
                    prog = self.build_shader_prog(prog_desc,
                                                  'image_widget_vertex_shader.glsl',
                                                  'image_widget_fragment_shader_template.glsl',
                                                  overlay_uniforms=overlay_uniforms,
                                                  getcolor_expression=self._getcolor_expression,
                                                  extra_transformation_expression='' if self._extra_transformation_expression is None else self._extra_transformation_expression,
                                                  do_overlay_blending=do_overlay_blending)
                prog.bind()
                estack.callback(prog.release)
                view = widget.view
                view.quad_buffer.bind()
                estack.callback(view.quad_buffer.release)
                view.quad_vao.bind()
                estack.callback(view.quad_vao.release)
                vert_coord_loc = prog.attributeLocation('vert_coord')
                prog.enableAttributeArray(vert_coord_loc)
                prog.setAttributeBuffer(vert_coord_loc, gl.GL_FLOAT, 0, 2, 0)
                prog.setUniformValue('tex', 0)
                frag_to_tex = Qt.QTransform()
                frame = Qt.QPolygonF(view.mapFromScene(Qt.QPolygonF(self.sceneTransform().mapToPolygon(self.boundingRect().toRect()))))
                if not qpainter.transform().quadToSquare(frame, frag_to_tex):
                    raise RuntimeError('Failed to compute gl_FragCoord to texture coordinate transformation matrix.')
                prog.setUniformValue('frag_to_tex', frag_to_tex)
                prog.setUniformValue('tex_global_alpha', self.opacity())
                prog.setUniformValue('viewport_height', float(widget.size().height()))

#               print('qpainter.transform():', qtransform_to_numpy(qpainter.transform()))
#               print('self.deviceTransform(view.viewportTransform()):', qtransform_to_numpy(self.deviceTransform(view.viewportTransform())))

                min_max = numpy.array((self._normalized_min, self._normalized_max), dtype=float)
                min_max = self._renormalize_for_gl(min_max)
                prog.setUniformValue('gamma', self.gamma)
                prog.setUniformValue('rescale_min', min_max[0])
                prog.setUniformValue('rescale_range', min_max[1] - min_max[0])
                for overlay_idx, overlay_item in enumerate(visible_overlays):
                    texture_unit = overlay_idx + 1 # +1 because first texture unit is occupied by image texture
                    overlay_item._update_tex(estack, texture_unit) 
                    frag_to_tex = Qt.QTransform()
                    frame = Qt.QPolygonF(view.mapFromScene(Qt.QPolygonF(overlay_item.sceneTransform().mapToPolygon(overlay_item.boundingRect().toRect()))))
                    qpainter_transform = overlay_item.deviceTransform(view.viewportTransform())
                    if not qpainter_transform.quadToSquare(frame, frag_to_tex):
                        raise RuntimeError('Failed to compute gl_FragCoord to texture coordinate transformation matrix for overlay {}.'.format(overlay_idx))
                    prog.setUniformValue('overlay{}_frag_to_tex'.format(overlay_idx), frag_to_tex)
                    prog.setUniformValue('overlay{}_tex'.format(overlay_idx), texture_unit)
                    prog.setUniformValue('overlay{}_tex_global_alpha'.format(overlay_idx), overlay_item.opacity())
                    prog.setUniformValue('overlay{}_gamma'.format(overlay_idx), overlay_item.gamma)
                    min_max[0], min_max[1] = overlay_item._normalized_min, overlay_item._normalized_max
                    min_max = overlay_item._renormalize_for_gl(min_max)
                    prog.setUniformValue('overlay{}_rescale_min'.format(overlay_idx), min_max[0])
                    prog.setUniformValue('overlay{}_rescale_range'.format(overlay_idx), min_max[1] - min_max[0])
                gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
                gl.glDrawArrays(gl.GL_TRIANGLE_FAN, 0, 4)
        self._paint_frame(qpainter)

    def hoverMoveEvent(self, event):
        if self._image is not None:
            # NB: event.pos() is a QPointF, and one may call QPointF.toPoint(), as in the following line,
            # to get a QPoint from it.  However, toPoint() rounds x and y coordinates to the nearest int,
            # which would cause us to erroneously report mouse position as being over the pixel to the
            # right and/or below if the view with the mouse cursor is zoomed in such that an image pixel
            # occupies more than one screen pixel and the cursor is over the right and/or bottom half
            # of a pixel.
#           pos = event.pos().toPoint()
            pos = Qt.QPoint(event.pos().x(), event.pos().y())
            cis = []
            ci = self.generate_contextual_info_for_pos(pos)
            if ci is not None:
                cis.append(ci)
            self._update_overlay_items_z_sort()
            for overlay_stack_idx, overlay_item in enumerate(self._overlay_items):
                if overlay_item.isVisible():
                    # For a number of potential reasons including overlay rotation, differing resolution
                    # or scale, and fractional offset relative to parent, it is necessary to project floating
                    # point coordinates and not integer coordinates into overlay item space in order to
                    # accurately determine which overlay image pixel contains the mouse pointer
                    o_pos = self.mapToItem(overlay_item, event.pos())
                    if overlay_item.boundingRect().contains(o_pos):
                        ci = overlay_item.generate_contextual_info_for_pos(o_pos, overlay_stack_idx)
                        if ci is not None:
                            cis.append(ci)
            self.scene().update_contextual_info('\n'.join(cis), self)

    def generate_contextual_info_for_pos(self, pos):
        if Qt.QRect(Qt.QPoint(), self._image.size).contains(pos):
            mst = 'x:{} y:{} '.format(pos.x(), pos.y())
            image_type = self._image.type
            vt = '(' + ' '.join((c + ':{}' for c in image_type)) + ')'
            vt = vt.format(self._image.data[pos.x(), pos.y()])
            return mst+vt

    def hoverLeaveEvent(self, event):
        self.scene().clear_contextual_info(self)

    def make_and_attach_overlay(self, overlay_image=None, overlay_image_data=None, overlay_image_data_T=None, overlay_name=None,
                                fill_overlayed_image_item_enabled=True, blend_function='screen', zValue=0, ImageOverlayItemClass=None):
        """If None is supplied for ImageOverlayItemClass, ImageOverlayItem is used."""
        ImageOverlayItemClass = ImageOverlayItem if ImageOverlayItemClass is None else ImageOverlayItemClass
        overlay_item = ImageOverlayItemClass(
            self, overlay_image, overlay_image_data, overlay_image_data_T, overlay_name,
            fill_overlayed_image_item_enabled, blend_function)
        overlay_item.setZValue(zValue)
        return overlay_item

    def attach_overlay(self, overlay_item):
        assert overlay_item not in self._overlay_items
        if not isinstance(overlay_item, ImageOverlayItem):
            raise ValueError('overlay_item argument must be or must be derived from ris_widget.image_scene.ImageOverlayItem.')
        if overlay_item.parentItem() is not self:
            raise RuntimeError('ImageItem must be parent of overlay_item to be attached.')
        overlay_item.zChanged.connect(self._on_overlay_z_changed)
        self.image_changing.connect(overlay_item._on_overlayed_image_changing)
        overlay_item.blend_function_changed.connect(self.update)
        overlay_item.trilinear_filtering_enabled_changed.connect(self.update)
        overlay_item.getcolor_expression_changed.connect(self.update)
        overlay_item.extra_transformation_expression_changed.connect(self.update)
        overlay_item.min_changed.connect(self.update)
        overlay_item.max_changed.connect(self.update)
        overlay_item.gamma_changed.connect(self.update)
        self._overlay_items.append(overlay_item)
        self._overlay_items_z_sort_is_current = False
        self.overlay_attaching.emit(overlay_item)
        self.update()

    def detach_overlay(self, overlay_item):
        assert overlay_item in self._overlay_items
        overlay_item.zChanged.disconnect(self._on_overlay_z_changed)
        self.image_changing.disconnect(overlay_item._on_overlayed_image_changing)
        overlay_item.blend_function_changed.disconnect(self.update)
        overlay_item.trilinear_filtering_enabled_changed.disconnect(self.update)
        overlay_item.getcolor_expression_changed.disconnect(self.update)
        overlay_item.extra_transformation_expression_changed.disconnect(self.update)
        overlay_item.min_changed.disconnect(self.update)
        overlay_item.max_changed.disconnect(self.update)
        overlay_item.gamma_changed.disconnect(self.update)
        self.overlay_detaching(overlay_item)
        idx = self._overlay_items.index(overlay_item)
        del self._overlay_items[idx]
        self.update()

    def _update_overlay_items_z_sort(self):
        if not self._overlay_items_z_sort_is_current:
            self._overlay_items.sort(key=lambda i: i.zValue())
            self._overlay_items_z_sort_is_current = True

    def _on_overlay_z_changed(self):
        self._overlay_items_z_sort_is_current = False

    @property
    def overlays(self):
        """A tuple of ImageOverlayItems in ascending Z value order."""
        self._update_overlay_items_z_sort()
        return tuple(self._overlay_items)

class ImageOverlayItem(ItemWithImage):
    QGRAPHICSITEM_TYPE = UNIQUE_QGRAPHICSITEM_TYPE()
    # Blend functions adapted from http://dev.w3.org/SVG/modules/compositing/master/ 
    _BLEND_FUNCTIONS = {
        'src-over' : ('dca = sca + dca * (1.0f - sa);',
                      'da = sa + da - sa * da;'),
        'dst-over' : ('dca = dca + sca * (1.0f - da);',
                      'da = sa + da - sa * da;'),
        'plus'     : ('dca += sca;',
                      'da += sa;'),
        'multiply' : ('dca = sca * dca + sca * (1.0f - da) + dca * (1.0f - sa);',
                      'da = sa + da - sa * da;'),
        'screen'   : ('dca = sca + dca - sca * dca;',
                      'da = sa + da - sa * da;'),
        'overlay'  : ('isa = 1.0f - sa; osa = 1.0f + sa;',
                      'ida = 1.0f - da; oda = 1.0f + da;',
                      'sada = sa * da;',
                      'for(i = 0; i < 3; ++i){',
                      '    dca[i] = (dca[i] + dca[i] <= da) ?',
                      '             (sca[i] + sca[i]) * dca[i] + sca[i] * ida + dca[i] * isa :',
                      '             sca[i] * oda + dca[i] * osa - (dca[i] + dca[i]) * sca[i] - sada;}',
                      'da = sa + da - sada;'),
        'difference':('dca = (sca * da + dca * sa - (sca + sca) * dca) + sca * (1.0f - da) + dca * (1.0f - sa);',
                      'da = sa + da - sa * da;')}
    for k, v in _BLEND_FUNCTIONS.items():
        _BLEND_FUNCTIONS[k] = '\n        ' + '\n        '.join(v)
    del k, v

    blend_function_changed = Qt.pyqtSignal()
    fill_overlayed_image_enabled_changed = Qt.pyqtSignal()

    def __init__(self, overlayed_image_item, overlay_image=None, overlay_image_data=None, overlay_image_data_T=None, overlay_name=None,
                 fill_overlayed_image_item_enabled=True, blend_function='screen'):
        super().__init__(overlayed_image_item)
        self._itemChange_handlers = {
            Qt.QGraphicsItem.ItemParentChange : self._on_itemParentChange,
            Qt.QGraphicsItem.ItemParentHasChanged : self._on_itemParentHasChanged,
            Qt.QGraphicsItem.ItemTransformChange : self._on_itemTransformChange,
            Qt.QGraphicsItem.ItemPositionChange : self._on_itemPositionChange,
            Qt.QGraphicsItem.ItemRotationChange : self._on_itemRotationChange,
            Qt.QGraphicsItem.ItemScaleChange : self._on_itemScaleChange}
        if sum(map(lambda v: v is not None, (overlay_image, overlay_image_data, overlay_image_data_T))) > 1:
            raise ValueError('At most one of overlay_image, overlay_image_data, or overlay_image_data_T may be specified.')
        self.setFlag(Qt.QGraphicsItem.ItemIgnoresParentOpacity)
        self.name = overlay_name
        if overlayed_image_item is not None:
            overlayed_image_item.attach_overlay(self)
        self._fill_overlayed_image_item_enabled = fill_overlayed_image_item_enabled
        self._allow_transform_change_with_fill_enabled = False
        self.setFlag(Qt.QGraphicsItem.ItemSendsGeometryChanges)
        self._frame_color = Qt.QColor(0,0,255,128)
        self._blend_function = blend_function
        self._blend_function_impl = ImageOverlayItem._BLEND_FUNCTIONS[self._blend_function]
        if overlay_image is not None:
            self.image = overlay_image
        elif overlay_image_data is not None:
            self.image_data = overlay_image_data
        elif overlay_image_data_T is not None:
            self.image_data_T = overlay_image_data_T

    def type(self):
        return ImageOverlayItem.QGRAPHICSITEM_TYPE

    def boundingRect(self):
        if self._image is None or self.parentItem()._image is None:
            return Qt.QRectF()
        return Qt.QRectF(Qt.QPointF(), Qt.QSizeF(self._image.size))

    def itemChange(self, change, value):
        ret = None
        try:
            ret = self._itemChange_handlers[change](change, value)
        except KeyError:
            pass
        # Omitting the following line results in numerous subtle misbehaviors such as being unable to make this item visible
        # after hiding it.  This is a result of the return value from itemChange sometimes mattering: certain item changes
        # may be cancelled or modified by returning something other than the value argument.  In the case of
        # Qt.QGraphicsItem.ItemVisibleChange, returning something that casts to False overrides a visibility -> True state
        # change, causing the item to remain hidden.
        return value if ret is None else ret

    def _on_itemParentChange(self, change, value):
        parent = self.parentItem()
        if parent is not None:
            parent.detach_overlay(self)
        if self.tex is not None and self.tex.isCreated():
            scene = self.scene()
            if scene is not None:
                views = scene.views()
                if views:
                    views[0].makeCurrent()
                    try:
                        self.tex.destroy()
                    finally:
                        views[0].doneCurrent()

    def _on_itemParentHasChanged(self, change, value):
        parent = value
        if parent is not None:
            parent.attach_overlay(self)

    def _on_itemTransformChange(self, change, value):
        # Do not allow any movement relative to parent if set to fill parent, except for when adjusting to new parent size
        if self._fill_overlayed_image_item_enabled and not self._allow_transform_change_with_fill_enabled:
            # At this instant, value contains the new transformation that something would like us to move to, and self.transform()
            # contains the current transformation.  In order to reject transitioning to the new transformation, we simply
            # return the current transformation, causing our current transformation to be replaced with itself.
            return self.transform()

    def _on_itemPositionChange(self, change, value):
        # Although their name suggests that listening for and rejecting ItemTransformChange notifications should be sufficient to
        # prevent any alteration of ImageOverlayItem's transformation matrix, ItemTransformChange notifications are dispatched
        # only when an item's transformation matrix is modified by a direct call to setTransform (as far as I can tell).  Therefore,
        # it is necessary to listen for and reject ItemTransformChange, ItemPositionChange, ItemRotationChange, and ItemScaleChange as
        # well.
        if self._fill_overlayed_image_item_enabled and not self._allow_transform_change_with_fill_enabled:
            # As with ItemTransformChange, returning the current position in response to ItemPositionChange causes the current
            # position to be replaced with itself and the proposed new position to be ignored.
            return self.pos()

    def _on_itemRotationChange(self, change, value):
        if self._fill_overlayed_image_item_enabled and not self._allow_transform_change_with_fill_enabled:
            # As with ItemTransformChange ...
            return self.rotation()

    def _on_itemScaleChange(self, change, value):
        if self._fill_overlayed_image_item_enabled and not self._allow_transform_change_with_fill_enabled:
            # As with ItemTransformChange ...
            return self.scale()

    def paint(self, qpainter, option, widget):
        """This item is primarily drawn by its parent, an ImageItem, in order that it may be composited with that ImageItem
        in more advanced ways than supported by QPainter when rendering to an OpenGL context (QPainter in software mode
        supports a galaxy of various blend modes, but QPainter in software mode is far too slow for our purposes, namely, 
        drawing full screen images transformed in real time - not unlike AGG, which would also be too slow.
        Use matplotlib.pyplot.imshow to see how slow is slow).
        
        The only drawing that ImageOverlayItem actually does in its own right is to paint a stippled border two pixels wide,
        vwith one pixel inside and one pixel outside, via the _paint_frame call below."""
        overlayed_image_item = self.parentItem()
        if self._image is not None and (overlayed_image_item is None or overlayed_image_item._image is not None):
            self._paint_frame(qpainter)

    def generate_contextual_info_for_pos(self, pos, overlay_stack_idx):
        pos = Qt.QPoint(pos.x(), pos.y())
        oimage = self._image
        if Qt.QRect(Qt.QPoint(), oimage.size).contains(pos):
            mst = 'overlay {}: '.format(overlay_stack_idx) if self.name is None else (self.name + ': ')
            mst+= 'x:{} y:{} '.format(pos.x(), pos.y())
            oimage_type = oimage.type
            vt = '(' + ' '.join((c + ':{}' for c in oimage_type)) + ')'
            if len(oimage_type) == 1:
                vt = vt.format(oimage.data[pos.x(), pos.y()])
            else:
                vt = vt.format(*oimage.data[pos.x(), pos.y()])
            return mst+vt

    def _on_image_changing(self, self_, old_image, new_image):
        super()._on_image_changing(self_, old_image, new_image)
        parent_image_item = self.parentItem()
        if parent_image_item is not None and \
           self._fill_overlayed_image_item_enabled and \
           new_image is not None and (old_image is None or old_image.size != new_image.size):
            self._do_fill_parent(self.parentItem())

    def _on_overlayed_image_changing(self, image_item, old_image, new_image):
        assert image_item is self.parentItem()
        if self._fill_overlayed_image_item_enabled and new_image is not None and (old_image is None or old_image.size != new_image.size):
            self._do_fill_parent()

    def _do_fill_parent(self, parent_image_item):
        t = Qt.QTransform()
        o_s = self._image.size
        i_s = parent_image_item._image.size
        t.scale(i_s.width() / o_s.width(), i_s.height() / o_s.height())
        self._allow_transform_change_with_fill_enabled = True
        try:
            self.setPos(0,0)
            self.setTransform(t)
        finally:
            self._allow_transform_change_with_fill_enabled = False

    def do_fill_parent(self):
        parent_image_item = self.parentItem()
        if parent_image_item is not None and self._image is not None:
            self._do_fill_parent(parent_image_item)

    def _blend_function_getter(self):
        return self._blend_function

    def _blend_function_setter(self, v):
        if v != self._blend_function:
            if v not in self._BLEND_FUNCTIONS:
                raise KeyError('The string assigned to .blend_function must be present in ._BLEND_FUNCTIONS.')
            self._blend_function = v
            self._blend_function_impl = self._BLEND_FUNCTIONS[v]
            self.blend_function_changed.emit()

    blend_function = property(_blend_function_getter, _blend_function_setter, doc='Must be one of:\n' + '\n'.join("'" + s + "'" for s in sorted(_BLEND_FUNCTIONS.keys())))

    @property
    def fill_overlayed_image_item_enabled(self):
        """If enabled, overlay is stretched to match the dimensions of the overlayed image, and all attempts
        to translate, scale, rotate, or otherwise change the overlay's transformation matrix are silently ignored."""
        return self._fill_overlayed_image_item_enabled

    @fill_overlayed_image_item_enabled.setter
    def fill_overlayed_image_item_enabled(self, v):
        v = bool(v)
        if v != self._fill_overlayed_image_item_enabled:
            if v:
                self._do_fill_parent(self.parentItem())
            self._fill_overlayed_image_item_enabled = v
            self.fill_overlayed_image_enabled_changed.emit()