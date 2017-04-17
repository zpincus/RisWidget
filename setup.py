#!/usr/bin/env python3

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
# Authors: Zach Pincus

import setuptools

setuptools.setup(
    package_data = {
        'ris_widget' : [
            'icons/checked_box_icon.svg',
            'icons/disabled_checked_box_icon.svg',
            'icons/disabled_pseudo_checked_box_icon.svg',
            'icons/disabled_unchecked_box_icon.svg',
            'icons/disabled_wrong_type_checked_box_icon.svg',
            'icons/image_icon.svg',
            'icons/layer_icon.svg',
            'icons/layer_stack_icon.svg',
            'icons/pseudo_checked_box_icon.svg',
            'icons/unchecked_box_icon.svg',
            'icons/wrong_type_checked_box_icon.svg',
            'shaders/histogram_item_fragment_shader.glsl',
            'shaders/layer_stack_item_fragment_shader_template.glsl',
            'shaders/planar_quad_vertex_shader.glsl'
        ]
    },
    name = 'ris_widget',
    packages = setuptools.find_packages(),
    install_requires=['cffi>=1.0.0', 'numpy', 'PyOpenGL', 'PyQt5'],
    setup_requires=['cffi>=1.0.0'],
    cffi_modules=['ris_widget/histogram/build_histogram.py:ffi'],
    version = '1.5')
