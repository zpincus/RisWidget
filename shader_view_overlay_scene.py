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

from PyQt5 import Qt

class ShaderViewOverlayScene(Qt.QGraphicsScene):
    def __init__(self, shader_scene, parent):
        super().__init__(parent)
        self.shader_scene = shader_scene
        self.mouseover_text_item = self.addText('')
        self.shader_scene.update_mouseover_info_signal.connect(self.on_update_mouseover_info)
        self.mouseover_text_item.setDefaultTextColor(Qt.QColor(Qt.Qt.white))

    def on_update_mouseover_info(self, string, is_html):
        if is_html:
            self.mouseover_text_item.setHtml(string)
        else:
            self.mouseover_text_item.setPlainText(string)

    def eventFilter(self, watched, event):
#       print(watched, type(event))
        if watched is self.shader_scene and issubclass(type(event), (Qt.QGraphicsSceneEvent, Qt.QKeyEvent, Qt.QFocusEvent, Qt.QTimerEvent)) or type(event) is Qt.QEvent and event.type() is Qt.QEvent.MetaCall:
#           if hasattr(event, 'screenPos') and issubclass(type(event), Qt.QGraphicsSceneEvent):
#               event.setScenePos(event.widget().mapFromGlobal(event.screenPos()))
#               print(event.screenPos(), event.widget().mapFromGlobal(event.screenPos()))
            return self.event(event)
        else:
            return super().eventFilter(watched, event)
