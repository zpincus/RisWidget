# This code is licensed under the MIT License (see LICENSE file for details)

from contextlib import ExitStack
import numpy
from PyQt5 import Qt
from string import Template
import textwrap
from .. import shared_resources
from . import shader_item


SRC_BLEND = '''    // blending function name: src
    dca = sca;
    da = s.a;
'''

UNIFORM_SECTION = Template(textwrap.dedent("""\
    uniform sampler2D tex_${tex_unit};
    uniform float rescale_min_${tex_unit};
    uniform float rescale_range_${tex_unit};
    uniform float gamma_${tex_unit};
    uniform vec4 tint_${tex_unit};"""))

COLOR_TRANSFORM = Template(textwrap.dedent("""\
    vec4 color_transform_${tex_unit}(vec4 in_, vec4 tint, float rescale_min, float rescale_range, float gamma_scalar)
    {
        vec4 out_;
        out_.a = in_.a;
        vec3 gamma = vec3(gamma_scalar, gamma_scalar, gamma_scalar);
        ${transform_section}
        return clamp(out_, 0, 1);
    }"""))

MAIN_SECTION = Template(textwrap.dedent("""\
        // layer_stack[${layer_index}]
        s = texture2D(tex_${tex_unit}, tex_coord);
        s = color_transform_${tex_unit}(${getcolor_expression}, tint_${tex_unit}, rescale_min_${tex_unit}, rescale_range_${tex_unit}, gamma_${tex_unit});
        sca = s.rgb * s.a;
    ${blend_function}
        da = clamp(da, 0, 1);
        dca = clamp(dca, 0, 1);
    """))


class LayerStackItem(shader_item.ShaderItem):
    """The layer_stack attribute of LayerStackItem is an SignalingList, a container with a list interface, containing a sequence
    of Layer instances (or instances of subclasses of Layer or some duck-type compatible thing).  In terms of composition ordering,
    these are in ascending Z-order, with the positive Z axis pointing out of the screen.  layer_stack should be manipulated via the
    standard list interface, which it implements completely.  So, for example, to place an layer at the top of the stack:

    LayerStackItem_instance.layer_stack.append(Layer(Image(numpy.zeros((400,400,3), dtype=numpy.uint8))))

    SignalingList emits signals when elements are removed, inserted, or replaced.  LayerStackItem responds to these signals
    in order to trigger repainting and otherwise keep its state consistent with that of its layer_stack attribute.  Users
    and extenders of LayerStackItem may do so in the same way: by connecting Python functions directly to
    LayerStackItem_instance.layer_stack.inserted, LayerStackItem_instance.layer_stack.removed, and
    LayerStackItem_instance.layer_stack.replaced.  For a concrete example, take a look at ImageStackWidget.

    The blend_function of the first (0th) element of layer_stack is ignored, although its getcolor_expression and
    extra_transformation expression, if provided, are used.  In the fragment shader, the result of applying getcolor_expression
    and then extra_transformation expression are saved in the variables da (a float representing alpha channel value) and dca
    (a vec3, which is a vector of three floats, representing the premultiplied RGB channel values).

    Subsequent elements of layer_stack are blended into da and dca using the blend_function specified by each Image.
    When no elements remain to be blended, dca is divided element-wise by da, un-premultiplying it, and these three values and
    da are returned to OpenGL for src-over blending into the view.

    LayerStackItem's boundingRect has its top left at (0, 0) and has same dimensions as the first (0th) element of layer_stack,
    or is 1000x1000 if layer_stack is empty.  Therefore, if the scale of an LayerStackItem instance containing at least one layer
    has not been modified, that LayerStackItem instance will be the same width and height in scene units as the first element
    of layer_stack is in pixel units, making the mapping between scene units and pixel units 1:1 for the layer at the bottom
    of the stack (ie, layer_stack[0])."""
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    DEFAULT_BOUNDING_RECT = Qt.QRectF(Qt.QPointF(0, 0), Qt.QSizeF(1000, 1000))
    TEXTURE_BORDER_COLOR = Qt.QColor(0, 0, 0, 0)

    bounding_rect_changed = Qt.pyqtSignal()
    new_image_painted = Qt.pyqtSignal()

    def __init__(self, layer_stack, parent_item=None):
        self._new_image = False
        super().__init__(parent_item)
        self.setAcceptHoverEvents(True)
        self.setFlag(Qt.QGraphicsItem.ItemIsFocusable)
        self.contextual_info_pos = None
        self._bounding_rect = Qt.QRectF(self.DEFAULT_BOUNDING_RECT)
        self.layer_stack = layer_stack
        layers = layer_stack.layers
        layers.inserted.connect(self._on_layers_inserted)
        layers.removed.connect(self._on_layers_removed)
        layers.replaced.connect(self._on_layers_replaced)
        self._attach_layers(layers)

        layer_stack.layer_focus_changed.connect(self._on_layer_focus_changed)
        layer_stack.solo_layer_mode_action.toggled.connect(self.update)

    def boundingRect(self):
        return self._bounding_rect

    def _attach_layers(self, layers):
        for layer in layers:
            layer.changed.connect(self.update)
            layer.image_changed.connect(self._on_layer_image_changed)

    def _detach_layers(self, layers):
        for layer in layers:
            # no need to keep track of case when layer shows up in the list multiple times: LayerStack prevents that
            layer.changed.disconnect(self.update)
            layer.image_changed.disconnect(self._on_layer_image_changed)

    def _base_layer_changed(self, old_base, new_base):
        has_base = new_base is not None and new_base.image is not None
        had_base = old_base is not None and old_base.image is not None
        if has_base != had_base or (has_base and new_base.image.size != old_base.image.size):
            self._change_bounding_rect(new_base.image if new_base is not None else None)

    def _change_bounding_rect(self, base_image):
        self.prepareGeometryChange()
        if base_image is None:
            self._bounding_rect = self.DEFAULT_BOUNDING_RECT
        else:
            self._bounding_rect = Qt.QRectF(Qt.QPointF(), Qt.QSizeF(base_image.size))
        self.bounding_rect_changed.emit()

    def _on_layers_inserted(self, layer_index, inserted_layers):
        if layer_index == 0:
            new_base = self.layer_stack.layers[0]
            if len(self.layer_stack.layers) > len(inserted_layers):
                old_base = self.layer_stack.layers[len(inserted_layers)]
            else:
                old_base = None
            self._base_layer_changed(old_base, new_base)
        self._attach_layers(inserted_layers)
        self.update()
        self._update_contextual_info()

    def _on_layers_removed(self, layer_indices, removed_layers):
        try:
            old_base_i = layer_indices.index(0)
        except ValueError:
            old_base_i = None
        if old_base_i is not None:
            if len(self.layer_stack.layers) > 0:
                new_base = self.layer_stack.layers[0]
            else:
                new_base = None
            old_base = removed_layers[old_base_i]
            self._base_layer_changed(old_base, new_base)
        self._detach_layers(removed_layers)
        self.update()
        self._update_contextual_info()

    def _on_layers_replaced(self, layer_indices, old_layers, new_layers):
        try:
            base_i = layer_indices.index(0)
        except ValueError:
            base_i = None
        if base_i is not None:
            new_base = new_layers[base_i]
            old_base = old_layers[base_i]
            self._base_layer_changed(old_base, new_base)
        self._detach_layers(old_layers)
        self._attach_layers(new_layers)
        self.update()
        self._update_contextual_info()

    def _on_layer_image_changed(self, layer):
        layer_index = self.layer_stack.layers.index(layer)
        if layer_index == 0:
            image = layer.image
            current_size = self.boundingRect().size()
            if image is None or Qt.QSizeF(image.size) != current_size:
                self._change_bounding_rect(image)
        self._update_contextual_info()
        self._new_image = True

    def _on_layer_focus_changed(self, old_layer, layer):
        # The appearence of a layer_stack_item may depend on which layer table row is current while
        # "examine layer mode" is enabled.
        if self.layer_stack.examine_layer_mode:
            self.update()

    def hoverMoveEvent(self, event):
        # NB: contextual info overlay will only be correct for the first view containing this item.
        self.contextual_info_pos = event.pos()
        self._update_contextual_info()

    def hoverLeaveEvent(self, event):
        self.contextual_info_pos = None
        self.scene().contextual_info_item.set_info_text(None)

    def _update_contextual_info(self):
        if self.layer_stack.examine_layer_mode:
            layer_index = self.layer_stack.focused_layer_layer_index
            visible_layer_indices = [] if layer_index is None else [layer_index]
        elif self.layer_stack.layers:
            visible_layer_indices = [layer_index for layer_index, layer in enumerate(self.layer_stack.layers) if layer.visible]
        else:
            visible_layer_indices = []
        if not visible_layer_indices or self.contextual_info_pos is None or self.scene() is None or not self.scene().views():
            self.scene().contextual_info_item.set_info_text(None)
            return
        fpos = self.contextual_info_pos
        ipos = Qt.QPoint(fpos.x(), fpos.y()) # don't use fpos.toPoint(): it rounds, but we need to truncate to get the right pixel if zoomed in
        cis = []
        layer_indices = [(layer_index, self.layer_stack.layers[layer_index]) for layer_index in visible_layer_indices]
        layer_index, layer = layer_indices[0]
        ci = layer.generate_contextual_info_for_pos(ipos.x(), ipos.y(),
            layer_index if len(self.layer_stack.layers) > 1 else None)
        if ci is not None:
            cis.append(ci)
        image = layer.image
        image0size = self.DEFAULT_BOUNDING_RECT.size() if image is None else image.size
        for layer_index, layer in layer_indices[1:]:
            # Because the aspect ratio of subsequent layers may differ from the first, fractional
            # offsets must be discarded only after projecting from lowest-layer pixel coordinates
            # to current layer pixel coordinates.  It is easy to see why in the case of an overlay
            # exactly half the width and height of the base: one base unit is two overlay units,
            # so dropping base unit fractions would cause overlay units to be rounded to the preceding
            # even number in any case where an overlay coordinate component should be odd.
            image = layer.image
            if image is None:
                ci = layer.generate_contextual_info_for_pos(None, None, layer_index)
            else:
                imagesize = image.size
                ci = layer.generate_contextual_info_for_pos(
                    int(fpos.x() * imagesize.width() / image0size.width()),
                    int(fpos.y() * imagesize.height() / image0size.height()),
                    layer_index)
            if ci is not None:
                cis.append(ci)
        self.scene().contextual_info_item.set_info_text('\n'.join(reversed(cis)))

    def paint(self, qpainter, option, widget):
        qpainter.beginNativePainting()
        with ExitStack() as estack:
            estack.callback(qpainter.endNativePainting)
            visible_layer_indices = self._get_visible_layer_indices_and_update_texs()
            if not visible_layer_indices:
                return
            layer_indices = [(tex_unit, layer_index, self.layer_stack.layers[layer_index]) for tex_unit, layer_index in enumerate(visible_layer_indices)]
            prog_desc = tuple((layer.getcolor_expression,
                               layer.blend_function if tex_unit > 0 else 'src',
                               layer.transform_section)
                              for tex_unit, layer_index, layer in layer_indices)
            if prog_desc in self.progs:
                prog = self.progs[prog_desc]
            else:
                uniforms = [UNIFORM_SECTION.substitute(tex_unit=tex_unit) for tex_unit, layer_index, layer in layer_indices]
                color_transforms = [COLOR_TRANSFORM.substitute(tex_unit=tex_unit, transform_section=layer.transform_section)
                                    for tex_unit, layer_index, layer in layer_indices]
                mains = [MAIN_SECTION.substitute(layer_index=layer_index, tex_unit=tex_unit,
                                                 getcolor_expression=layer.getcolor_expression,
                                                 blend_function=layer.BLEND_FUNCTIONS[layer.blend_function] if tex_unit > 0 else SRC_BLEND)
                         for tex_unit, layer_index, layer in layer_indices]

                prog = self.build_shader_prog(
                    prog_desc,
                    'planar_quad_vertex_shader',
                    'layer_stack_item_fragment_shader_template',
                    uniforms='\n'.join(uniforms),
                    color_transforms='\n'.join(color_transforms),
                    main='\n'.join(mains))
            prog.bind()
            estack.callback(prog.release)
            if widget is None:
                # We are being called as a result of a BaseView.snapshot(..) invocation
                widget = self.scene().views()[0].gl_widget
            glQuad = shared_resources.GL_QUAD()
            glQuad.buffer.bind()
            estack.callback(glQuad.buffer.release)
            glQuad.vao.bind()
            estack.callback(glQuad.vao.release)
            vert_coord_loc = prog.attributeLocation('vert_coord')
            prog.enableAttributeArray(vert_coord_loc)
            QGL = shared_resources.QGL()
            prog.setAttributeBuffer(vert_coord_loc, QGL.GL_FLOAT, 0, 2, 0)
            prog.setUniformValue('viewport_height', QGL.glGetFloatv(QGL.GL_VIEWPORT)[3])
            prog.setUniformValue('layer_stack_item_opacity', self.opacity())
            # The next few lines of code compute frag_to_tex, representing an affine transform in 2D space from pixel coordinates
            # to normalized (unit square) texture coordinates.  That is, matrix multiplication of frag_to_tex and homogenous
            # pixel coordinate vector <x, max_y-y, w> (using max_y-y to invert GL's Y axis which is upside-down, typically
            # with 1 for w) yields <x_t, y_t, w_t>.  In non-homogenous coordinates, that's <x_t/w_t, y_t/w_t>, which is
            # ready to be fed to the GLSL texture2D call.
            #
            # So, GLSL's Texture2D accepts 0-1 element-wise-normalized coordinates (IE, unit square, not unit circle), and
            # frag_to_tex maps from view pixel coordinates to texture coordinates.  If either element of the resulting coordinate
            # vector is outside the interval [0,1], the associated pixel in the view is outside of LayerStackItem.
            #
            # Frame represents, in screen pixel coordinates with origin at the top left of the view, the virtual extent of
            # the rectangular region containing LayerStackItem.  This rectangle may extend beyond any combination of the view's
            # four edges.
            #
            # Frame is computed from LayerStackItem's boundingRect, which is computed from the dimensions of the lowest
            # layer of the layer_stack, layer_stack[0].  Therefore, it is this lowest layer that determines the aspect
            # ratio of the unit square's projection onto the view.  Any subsequent layers in the stack use this same projection,
            # with the result that they are stretched to fill the LayerStackItem.
            frag_to_tex = Qt.QTransform()
            frame = Qt.QPolygonF(widget.view.mapFromScene(Qt.QPolygonF(self.sceneTransform().mapToPolygon(self.boundingRect().toRect()))))
            dpi_ratio = widget.devicePixelRatio()
            if dpi_ratio != 1:
                dpi_transform = Qt.QTransform()
                dpi_transform.scale(dpi_ratio, dpi_ratio)
                frame = dpi_transform.map(frame)
            if not qpainter.transform().quadToSquare(frame, frag_to_tex):
                raise RuntimeError('Failed to compute gl_FragCoord to texture coordinate transformation matrix.')
            prog.setUniformValue('frag_to_tex', frag_to_tex)
            min_max = numpy.empty((2,), dtype=float)
            for tex_unit, layer_index, layer in layer_indices:
                image = layer.image
                min_max[0], min_max[1] = layer.min, layer.max
                min_max = self._normalize_for_gl(min_max, image)
                prog.setUniformValue(f'tex_{tex_unit}', tex_unit)
                rescale_min = min_max[0]
                rescale_range = min_max[1] - min_max[0]
                if rescale_range == 0:
                    # make it so same-color images appear pure white if values
                    # are > 0, and black otherwise.
                    rescale_min = 0
                    rescale_range = max(0, min_max[0])
                prog.setUniformValue(f'rescale_min_{tex_unit}', rescale_min)
                prog.setUniformValue(f'rescale_range_{tex_unit}', rescale_range)
                prog.setUniformValue(f'gamma_{tex_unit}', layer.gamma)
                prog.setUniformValue(f'tint_{tex_unit}', Qt.QVector4D(*layer.tint))
            self.set_blend(estack)
            QGL.glEnableClientState(QGL.GL_VERTEX_ARRAY)
            QGL.glDrawArrays(QGL.GL_TRIANGLE_FAN, 0, 4)
        if self._new_image:
            self.new_image_painted.emit()
            self._new_image = False

    @staticmethod
    def _normalize_for_gl(v, image):
        """Some things to note:
        * OpenGL normalizes uint16 data uploaded to float32 texture for the full uint16 range.  We store
        our unpacked 12-bit images in uint16 arrays.  Therefore, OpenGL will normalize by dividing by
        65535, even though no 12-bit image will have a component value larger than 4095.
        * float32 data uploaded to float32 texture is not normalized"""
        if image.data.dtype == numpy.uint16:
            v /= 65535
        elif image.data.dtype == numpy.uint8 or image.data.dtype == bool:
            v /= 255
        elif image.data.dtype == numpy.float32:
            pass
        else:
            raise NotImplementedError('OpenGL-compatible normalization for {} missing.'.format(image.data.dtype))
        return v

    def _get_visible_layer_indices_and_update_texs(self):
        """Meant to be executed between a pair of QPainter.beginNativePainting() QPainter.endNativePainting() calls or,
        at the very least, when an OpenGL context is current, _get_visible_layer_indices_and_update_texs does whatever is required,
        for every visible layer with non-None .layer in self.layer_stack, in order that self._texs[layer] represents layer, including texture
        object creation and texture data uploading, and it leaves self._texs[layer] bound to texture unit n, where n is
        the associated visible_layer_index."""
        layer_stack = self.layer_stack
        if layer_stack.examine_layer_mode:
            layer_index = layer_stack.focused_layer_layer_index
            visible_layer_indices = [] if layer_index is None or layer_stack.layers[layer_index].image is None else [layer_index]
        elif layer_stack.layers:
            visible_layer_indices = [layer_index for layer_index, layer in enumerate(layer_stack.layers) if layer.visible and layer.image is not None]
        else:
            visible_layer_indices = []
        bound = set()
        for tex_unit, layer_index in enumerate(visible_layer_indices):
            texture = layer_stack.layers[layer_index].texture
            if texture not in bound:
                texture.bind(tex_unit)
                bound.add(texture)
        return visible_layer_indices