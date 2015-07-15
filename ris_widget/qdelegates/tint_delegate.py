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

class TintDelegate(Qt.QStyledItemDelegate):
    def createEditor(self, parent, option, midx):
        if midx.isValid():
            e = Qt.QColorDialog(parent)
            e.setOptions(Qt.QColorDialog.ShowAlphaChannel)# | Qt.QColorDialog.NoButtons)
            return e

    def setEditorData(self, e, midx):
        d = midx.data()
        if isinstance(d, Qt.QVariant):
            d = d.value()
        e.setCurrentColor(Qt.QColor(*(int(c*255) for c in d)))

    def setModelData(self, e, model, midx):
        color = e.currentColor()
        model.setData(midx, (color.redF(), color.greenF(), color.blueF(), color.alphaF()))