# This code is licensed under the MIT License (see LICENSE file for details)

import pkg_resources

from PyQt5 import Qt
import string
from .. import shared_resources


class ShaderItem(Qt.QGraphicsObject):
    def __init__(self, parent=None):
        Qt.QGraphicsObject.__init__(self, parent)
        self.progs = {}

    # all subclasses MUST define their own unique QGRAPHICSITEM_TYPE
    QGRAPHICSITEM_TYPE = shared_resources.generate_unique_qgraphicsitem_type()
    def type(self):
        return self.QGRAPHICSITEM_TYPE

    def build_shader_prog(self, desc, vert_name, frag_name, **frag_template_mapping):

        vert_src = pkg_resources.resource_string(__name__, 'shaders/{}.glsl'.format(vert_name))
        frag_src = pkg_resources.resource_string(__name__, 'shaders/{}.glsl'.format(frag_name))

        prog = Qt.QOpenGLShaderProgram(self)

        if not prog.addShaderFromSourceCode(Qt.QOpenGLShader.Vertex, vert_src):
            raise RuntimeError('Failed to compile vertex shader "{}" for {} {} shader program.'.format(vert_name, type(self).__name__, desc))

        if frag_template_mapping:
            frag_template = string.Template(frag_src.decode('ascii'))
            frag_src = frag_template.substitute(frag_template_mapping)

        if not prog.addShaderFromSourceCode(Qt.QOpenGLShader.Fragment, frag_src):
            raise RuntimeError('Failed to compile fragment shader "{}" for {} {} shader program.'.format(frag_name, type(self).__name__, desc))

        if not prog.link():
            raise RuntimeError('Failed to link {} {} shader program.'.format(type(self).__name__, desc))
        self.progs[desc] = prog
        return prog

    def set_blend(self, estack):
        """set_blend(estack) sets OpenGL blending mode to the most commonly required state and appends
        callbacks to estack that eventually return OpenGL blending to the state preceeding the call
        to set_blend.  Specifically, fragment shader RGB output is source-over alpha blended into the
        framebuffer, whereas the alpha channel is max(shader_alpha, framebuffer_alpha)."""
        # Blend ShaderItem fragment shader output with framebuffer as usual for RGB channels, blendedRGB = ShaderRGB * ShaderAlpha + BufferRGB * (1 - ShaderAlpha).
        # However, do not blend ShaderAlpha into BlendedAlpha.  Instead, BlendedAlpha = max(ShaderAlpha, BufferAlpha).  We can count on BufferAlpha always being saturated,
        # so this combination of alpha src and dst blend funcs and alpha blend equation results in framebuffer alpha remaining saturated - ie, opaque.  This is desired as
        # any transparency in the viewport framebuffer is taken by Qt to indicate viewport transparency, causing sceen content behind the viewport to be blended in, which
        # we do no want.  We are interested in blending over the scene - not blending the scene over the desktop!  So, it does make sense that we want to discard
        # transparency data immediately after it has been used to blend into the scene.  In fact, this is what Qt does when drawing partially transparent QGraphicsItems:
        # they are blended into the viewport framebuffer, but alpha is discarded and framebuffer alpha remains saturated.  This does require us to clear the framebuffer
        # with saturated alpha at the start of each frame, which we do by default (see ris_widget.qgraphicsviews.base_view.BaseView and its drawBackground method).
        QGL = shared_resources.QGL()
        if not QGL.glIsEnabled(QGL.GL_BLEND):
            QGL.glEnable(QGL.GL_BLEND)
            estack.callback(lambda: QGL.glDisable(QGL.GL_BLEND))
        desired_bfs = QGL.GL_SRC_ALPHA, QGL.GL_ONE_MINUS_SRC_ALPHA, QGL.GL_ONE, QGL.GL_ONE
        bfs = QGL.glGetIntegerv(QGL.GL_BLEND_SRC_RGB), QGL.glGetIntegerv(QGL.GL_BLEND_DST_RGB), QGL.glGetIntegerv(QGL.GL_BLEND_SRC_ALPHA), QGL.glGetIntegerv(QGL.GL_BLEND_DST_ALPHA)
        if bfs != desired_bfs:
            QGL.glBlendFuncSeparate(*desired_bfs)
            estack.callback(lambda: QGL.glBlendFuncSeparate(*bfs))
        desired_bes = QGL.GL_FUNC_ADD, QGL.GL_MAX
        bes = QGL.glGetIntegerv(QGL.GL_BLEND_EQUATION_RGB), QGL.glGetIntegerv(QGL.GL_BLEND_EQUATION_ALPHA)
        if bes != desired_bes:
            QGL.glBlendEquationSeparate(*desired_bes)
            estack.callback(lambda: QGL.glBlendEquationSeparate(*bes))