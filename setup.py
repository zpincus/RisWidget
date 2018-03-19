# This code is licensed under the MIT License (see LICENSE file for details)

import setuptools

setuptools.setup(
    name = 'ris_widget',
    packages = setuptools.find_packages(),
    package_data = {'ris_widget.qgraphicsitems': ['shaders/*.glsl'],
                    'ris_widget':['icon.svg']},
    install_requires=['cffi>=1.0.0', 'numpy', 'PyOpenGL', 'PyQt5'],
    setup_requires=['cffi>=1.0.0'],
    cffi_modules=['ris_widget/histogram/build_histogram.py:ffibuilder'],
    version = '1.5')
