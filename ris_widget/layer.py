# The MIT License (MIT)
#
# Copyright (c) 2015 WUSTL ZPLAB
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

from PyQt5 import Qt
import textwrap
import warnings
import numpy

from .image import Image
from .om import qt_property
from . import histogram


SHADER_PROP_HELP = """The GLSL fragment shader used to render an image within a layer stack is created
by filling in the $-values from the following template (somewhat simplified) with the corresponding
attributes of the layer. A template for layer in the stack is filled in and the
final shader is the the concatenation of all the templates.

NB: In case of error, calling del on the layer attribute causes it to revert to the default value.

    // Simplified GLSL shader code:
    // Below repeated for each layer
    uniform sampler2D tex;

    vec4 color_transform(vec4 in_, vec4 tint, float rescale_min, float rescale_range, float gamma_scalar)
    {
        vec4 out_;
        out_.a = in_.a;
        vec3 gamma = vec3(gamma_scalar, gamma_scalar, gamma_scalar);
        ${transform_section}
        // default value for transform_section:
        // out_.rgb = pow(clamp((in_.rgb - rescale_min) / (rescale_range), 0.0f, 1.0f), gamma); out_.rgba *= tint;
        return clamp(out_, 0, 1);
    }

    s = texture2D(tex, tex_coord);
    s = color_transform(
        ${getcolor_expression}, // default getcolor_expression for a grayscale image is: vec4(s.rrr, 1.0f)
        ${tint}, // [0,1] normalized RGBA component values that scale results of getcolor_expression
        rescale_min, // [0,1] scaled version of layer.min
        rescale_range, // [0,1] scaled version of layer.max - layer.min
        ${gamma});
    sca = s.rgb * s.a;
    ${Layer.BLEND_FUNCTIONS[${blend_function}]}
    da = clamp(da, 0, 1);
    dca = clamp(dca, 0, 1);

    // end per-layer repeat

    gl_FragColor = vec4(dca / da, da * layer_stack_item_opacity);"""

def coerce_to_str(v):
    return '' if v is None else str(v)

def coerce_to_tint(v):
    v = tuple(map(float, v))
    if len(v) not in (3,4) or not all(map(lambda v_: 0 <= v_ <= 1, v)):
        raise ValueError('The iteraterable assigned to tint must represent 3 or 4 real numbers in the interval [0, 1].')
    if len(v) == 3:
        v += (1.0,)
    return v

class Layer(qt_property.QtPropertyOwner):
    """Image's properties are all either computed from that ndarray, provide views into that ndarray's data (in the case of .data
    and .data_T), or, in the special cases of .is_twelve_bit for uint16 images and .imposed_float_range for floating-point images,
    represent unenforced constraints limiting the domain of valid values that are expected to be assumed by elements of the ndarray.

    Layer adds properties such as min/max/gamma scaling that control presentation of the image data contained by Image.

    In summary,
    Image: raw image data and essential information for interpreting that data in any context
    Layer: has an Image and presentation data and metadata for RisWidget such as rescaling min/max/gamma values and an informative name

    The changed signal is emitted when any property impacting image presentation is modified or image data is explicitly changed or refreshed.
    In the case where any image appearance change should cause a function to be executed, do changed.connect(your_function) rather than
    min_changed.connect(your_function); max_changed.connect(your_function); etc.

    Although Layer uses Property descriptors, subclasses adding properties are not obligated to use Property to represent the additional
    properties.  The regular @property decorator syntax or property(..) builtin remain available - Property provides an abstraction that
    is potentially convenient and worth understanding and using when defining a large number of properties."""

    GAMMA_RANGE = (0.0625, 16.0)
    IMAGE_TYPE_TO_GETCOLOR_EXPRESSION = {
        'G'   : 'vec4(s.rrr, 1.0f)',
        'Ga'  : 'vec4(s.rrr, s.g)',
        'rgb' : 'vec4(s.rgb, 1.0f)',
        'rgba': 's'}
    DEFAULT_TRANSFORM_SECTION = 'out_.rgb = pow(clamp((in_.rgb - rescale_min) / (rescale_range), 0.0f, 1.0f), gamma); out_.rgba *= tint;'
    # Blend functions adapted from http://dev.w3.org/SVG/modules/compositing/master/
    BLEND_FUNCTIONS = {
        'normal'   : ('dca = sca + dca * (1.0f - s.a);', # AKA src-over
                      'da = s.a + da - s.a * da;'),
        'multiply' : ('dca = sca * dca + sca * (1.0f - da) + dca * (1.0f - s.a);',
                      'da = s.a + da - s.a * da;'),
        'screen'   : ('dca = sca + dca - sca * dca;',
                      'da = s.a + da - s.a * da;'),
        'overlay'  : ('isa = 1.0f - s.a; osa = 1.0f + s.a;',
                      'ida = 1.0f - da; oda = 1.0f + da;',
                      'sada = s.a * da;',
                      'for(i = 0; i < 3; ++i){',
                      '    dca[i] = (dca[i] + dca[i] <= da) ?',
                      '             (sca[i] + sca[i]) * dca[i] + sca[i] * ida + dca[i] * isa :',
                      '             sca[i] * oda + dca[i] * osa - (dca[i] + dca[i]) * sca[i] - sada;}',
                      'da = s.a + da - sada;'),
        # 'src' :      ('dca = sca;',
        #               'da = s.a;'),
        # 'dst-over' : ('dca = dca + sca * (1.0f - da);',
        #               'da = s.a + da - s.a * da;'),
        # 'plus'     : ('dca += sca;',
        #               'da += s.a;'),
        # 'difference':('dca = (sca * da + dca * s.a - (sca + sca) * dca) + sca * (1.0f - da) + dca * (1.0f - s.a);',
        #               'da = s.a + da - s.a * da;')
    }
    for k, v in BLEND_FUNCTIONS.items():
        BLEND_FUNCTIONS[k] = '    // blending function name: {}\n    '.format(k) + '\n    '.join(v)
    del k, v
    # A change to any mutable property, including .image, potentially impacts layer presentation.  For convenience, .changed is emitted whenever
    # any mutable-property-changed signal is emitted, including or calling .image.refresh().
    # NB: .image_changed is the more specific signal emitted in addition to .changed for modifications to .image.
    #
    changed = Qt.pyqtSignal(object)
    image_changed = Qt.pyqtSignal(object)
    opacity_changed = Qt.pyqtSignal(object)

    def __init__(self, image=None, parent=None):
        self._retain_auto_min_max_enabled_on_min_max_change = False
        self._image = None
        super().__init__(parent)
        self.image_changed.connect(self.changed)
        self.image = image
        self.mask_radius = None

    def __repr__(self):
        image = self.image
        return '{}; {}image={}>'.format(
            super().__repr__()[:-1],
            'visible=False, ' if not self.visible else '',
            'None' if image is None else image.__repr__())

    @classmethod
    def from_savable_properties_dict(cls, prop_dict):
        ret = cls()
        for pname, pval, in prop_dict.items():
            setattr(ret, pname, pval)
        return ret

    def get_savable_properties_dict(self):
        ret = {name : prop.__get__(self) for name, prop in self._properties.items() if not prop.is_default(self)}
        return ret

    @property
    def image(self):
        return self._image

    @image.setter
    def image(self, v):
        if v is not self._image:
            if v is not None:
                if not isinstance(v, Image):
                    v = Image(v)
                try:
                    v.changed.connect(self._on_image_changed)
                except Exception as e:
                    if self._image is not None:
                        self._image.changed.disconnect(self._on_image_changed)
                    self._image = None
                    raise e
            if self._image is not None:
                self._image.changed.disconnect(self._on_image_changed)
            self._image = v
            if v is not None:
                self.dtype = v.data.dtype
                self.type = v.type
                self.size = v.size
            else:
                self.dtype = None
                self.type = None
                self.size = None
            self._on_image_changed(v)

    def _on_image_changed(self, image):
        assert image is self.image
        if image is not None:
            self.calculate_histogram()
            if self.auto_min_max_enabled:
                self.do_auto_min_max()
            else:
                l, h = image.valid_range
                if self.min < l:
                    self.min = l
                if self.max > h:
                    self.max = h
        self._update_property_defaults()
        self.image_changed.emit(self)

    def calculate_histogram(self):
        image = self.image
        r_min = None if self._is_default('histogram_min') else self.histogram_min
        r_max = None if self._is_default('histogram_max') else self.histogram_max
        self.image_min, self.image_max, self.histogram = histogram.histogram(image.data, (r_min, r_max), image.image_bits, self.mask_radius)


    def generate_contextual_info_for_pos(self, x, y, idx=None):
        image = self.image
        if image is None:
            image_text = 'None'
        else:
            image_text = image.generate_contextual_info_for_pos(x, y)
            if image_text is None:
                return
        ts = []
        if idx is not None:
            ts.append('{: 3}'.format(idx))
        t = ' '.join(ts)
        if t:
            t += ': '
        t += image_text
        return t

    def do_auto_min_max(self):
        assert self.image is not None
        self._retain_auto_min_max_enabled_on_min_max_change = True
        try:
            self.min = max(self.image_min, self.histogram_min)
            self.max = min(self.image_max, self.histogram_max)
        finally:
            self._retain_auto_min_max_enabled_on_min_max_change = False

    visible = qt_property.Property(
        default_value=True,
        coerce_arg_fn=bool)

    def _auto_min_max_enabled_post_set(self, v):
        if v and self.image is not None:
            self.do_auto_min_max()

    auto_min_max_enabled = qt_property.Property(
        default_value=False,
        coerce_arg_fn=bool,
        post_set_callback=_auto_min_max_enabled_post_set)

    def _min_default(self):
        if self.image is None:
            return 0.0
        else:
            return self._histogram_min_default()

    def _max_default(self):
        if self.image is None:
            return 65535.0
        else:
            return self._histogram_max_default()

    def _min_max_pre_set(self, v):
        if self.image is not None:
            l, h = self.image.valid_range
            if not l <= v <= h:
                warnings.warn('min/max values for this image must be in the closed interval [{}, {}].'.format(*r))
                return False

    def _min_post_set(self, v):
        if v > self.max:
            self.max = v
        if not self._retain_auto_min_max_enabled_on_min_max_change:
            self.auto_min_max_enabled = False

    def _max_post_set(self, v):
        if v < self.min:
            self.min = v
        if not self._retain_auto_min_max_enabled_on_min_max_change:
            self.auto_min_max_enabled = False

    min = qt_property.Property(
        default_value=_min_default,
        coerce_arg_fn=float,
        pre_set_callback=_min_max_pre_set,
        post_set_callback =_min_post_set)

    max = qt_property.Property(
        default_value=_max_default,
        coerce_arg_fn=float,
        pre_set_callback=_min_max_pre_set,
        post_set_callback=_max_post_set)

    def _gamma_pre_set(self, v):
        r = self.GAMMA_RANGE
        if not r[0] <= v <= r[1]:
            warnings.warn('gamma value must be in the closed interval [{}, {}].'.format(*r))
            return False

    gamma = qt_property.Property(
        default_value=1.0,
        coerce_arg_fn=float,
        pre_set_callback=_gamma_pre_set)

    def _histogram_min_default(self):
        if self.image is None:
            return 0.0
        elif self.dtype == numpy.float32:
            return self.image_min
        else:
            return float(self.image.valid_range[0])

    def _histogram_max_default(self):
        if self.image is None:
            return 65535.0
        elif self.dtype == numpy.float32:
            return self.image_max
        else:
            return float(self.image.valid_range[1])

    def _histogram_min_pre_set(self, v):
        l, h = (0, 65535.0) if self.image is None else self.image.valid_range
        if not l <= v <= h:
            warnings.warn('histogram_min value must be in [{}, {}].'.format(l, h))
            return False
        if v >= self.histogram_max:
            warnings.warn('histogram_min must be less than histogram_max.')
            return False

    def _histogram_max_pre_set(self, v):
        l, h = (0, 65535.0) if self.image is None else self.image.valid_range
        if not l <= v <= h:
            warnings.warn('histogram_max value must be in [{}, {}].'.format(l, h))
            return False
        if v <= self.histogram_min:
            warnings.warn('histogram_max must be greater than histogram_min.')
            return False

    def _histogram_min_max_post_set(self, v):
        if self.min < self.histogram_min:
            self.min = self.histogram_min
        if self.max > self.histogram_max:
            self.max = self.histogram_max

    histogram_min = qt_property.Property(
        default_value=_histogram_min_default,
        coerce_arg_fn=float,
        pre_set_callback=_histogram_min_pre_set,
        post_set_callback=_histogram_min_max_post_set)

    histogram_max = qt_property.Property(
        default_value=_histogram_max_default,
        coerce_arg_fn=float,
        pre_set_callback=_histogram_max_pre_set,
        post_set_callback=_histogram_min_max_post_set)

    trilinear_filtering_enabled = qt_property.Property(
        default_value=True,
        coerce_arg_fn=bool)

    def _getcolor_expression_default(self):
        image = self.image
        if image is None:
            return ''
        else:
            return self.IMAGE_TYPE_TO_GETCOLOR_EXPRESSION[image.type]

    getcolor_expression = qt_property.Property(
        default_value=_getcolor_expression_default,
        coerce_arg_fn=coerce_to_str,
        doc=SHADER_PROP_HELP)

    def _tint_pre_set(self, v):
        if self.tint[3] != v:
            self.opacity_changed.emit(self)

    tint = qt_property.Property(
        default_value=(1.0, 1.0, 1.0, 1.0),
        coerce_arg_fn=coerce_to_tint,
        pre_set_callback=_tint_pre_set,
        doc = SHADER_PROP_HELP)

    transform_section = qt_property.Property(
        default_value=DEFAULT_TRANSFORM_SECTION,
        coerce_arg_fn=coerce_to_str,
        doc=SHADER_PROP_HELP)

    def _blend_function_pre_set(self, v):
        if v not in self.BLEND_FUNCTIONS:
            raise ValueError('The string assigned to blend_function must be one of:\n' + '\n'.join("'" + s + "'" for s in sorted(self.BLEND_FUNCTIONS.keys())))

    blend_function = qt_property.Property(
        default_value='screen',
        coerce_arg_fn=str,
        pre_set_callback=_blend_function_pre_set,
        doc=SHADER_PROP_HELP + '\n\nSupported blend_functions:\n    ' + '\n    '.join("'" + s + "'" for s in sorted(BLEND_FUNCTIONS.keys())))

    name = qt_property.Property(
        default_value='',
        coerce_arg_fn=str)

    @property
    def opacity(self):
        return self.tint[3]

    @opacity.setter
    def opacity(self, v):
        v = float(v)
        if not 0 <= v <= 1:
            raise ValueError('The value assigned to opacity must be a real number in the interval [0, 1].')
        t = list(self.tint)
        t[3] = v
        self.tint = t #NB: tint takes care of emitting opacity_changed

