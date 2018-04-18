from PyQt5 import Qt
from ris_widget import ris_widget
import numpy

rw = ris_widget.RisWidgetQtObject()
timer = Qt.QTimer()
im = numpy.zeros((2560, 2160), dtype=numpy.uint16, order='F')
im[::3,::2] = 2**7

def advance():
    rw.image = im

timer.timeout.connect(advance)
advance() # WTF: faster if advance before show
rw.show()
rw.fps_display_dock_widget.show()
rw.image_view.zoom_to_fit_action.trigger()
timer.start(20)
rw.qapp.exec()
