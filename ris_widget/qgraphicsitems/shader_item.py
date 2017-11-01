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
        GL = shared_resources.QGL()
        if not GL.glIsEnabled(GL.GL_BLEND):
            GL.glEnable(GL.GL_BLEND)
            estack.callback(lambda: GL.glDisable(GL.GL_BLEND))
        desired_bfs = GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE
        bfs = GL.glGetIntegerv(GL.GL_BLEND_SRC_RGB), GL.glGetIntegerv(GL.GL_BLEND_DST_RGB), GL.glGetIntegerv(GL.GL_BLEND_SRC_ALPHA), GL.glGetIntegerv(GL.GL_BLEND_DST_ALPHA)
        if bfs != desired_bfs:
            GL.glBlendFuncSeparate(*desired_bfs)
            estack.callback(lambda: GL.glBlendFuncSeparate(*bfs))
        desired_bes = GL.GL_FUNC_ADD, GL.GL_MAX
        bes = GL.glGetIntegerv(GL.GL_BLEND_EQUATION_RGB), GL.glGetIntegerv(GL.GL_BLEND_EQUATION_ALPHA)
        if bes != desired_bes:
            GL.glBlendEquationSeparate(*desired_bes)
            estack.callback(lambda: GL.glBlendEquationSeparate(*bes))