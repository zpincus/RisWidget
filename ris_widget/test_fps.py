# This code is licensed under the MIT License (see LICENSE file for details)

import threading
import itertools
import time
import numpy
from PyQt5 import Qt

class _FPSTester:
    def __init__(self, images, rw):
        self.images = images
        self.rw = rw

    def start(self):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()

    def sleep_interval(self):
        interval = self.rw.qt_object.fps_display.last_interval
        if interval is None or interval > 0.1:
            interval = 1/20
        return max(0, interval - 0.01)

class _BGFPSTester(threading.Thread, _FPSTester):
    def __init__(self, images, rw):
        self.running = True
        threading.Thread.__init__(self, daemon=True)
        _FPSTester.__init__(self, images, rw)

    def run(self):
        while self.running:
            self.switch_image(next(self.images))
            time.sleep(self.sleep_interval())

    def stop(self):
        self.running = False
        self.join()

    def switch_image(self, image):
        raise NotImplementedError()

class ImageSetterFPSTester(_BGFPSTester):
    def switch_image(self, image):
        self.rw.image = image

class _SignalReceiver(Qt.QObject):
    NEW_IMAGE_EVENT = Qt.QEvent.registerEventType()

    def post(self, rw, image):
        e = Qt.QEvent(self.NEW_IMAGE_EVENT)
        e.rw = rw
        e.image = image
        Qt.QCoreApplication.postEvent(self, e)

    def event(self, e):
        if e.type() == self.NEW_IMAGE_EVENT:
            e.rw.image = e.image
            return True
        return super().event(e)

class QEventFPSTester(_BGFPSTester):
    def __init__(self, images, rw):
        self.receiver = _SignalReceiver()
        super().__init__(images, rw)

    def switch_image(self, image):
        self.receiver.post(self.rw, image)

class QTimerFPSTester(_FPSTester):
    def start(self):
        self.t = Qt.QTimer()
        self.t.timeout.connect(self.next_image)
        self.t.start(1000/40)

    def next_image(self):
        self.rw.image = next(self.images)

    def stop(self):
        self.t.stop()

class DirectFPSTester(_FPSTester):
    def start(self):
        print('press control-c to end test')
        while True:
            self.rw.image = next(self.images)
            self.rw.update()
            time.sleep(self.sleep_interval())

    def stop(self):
        pass

def test_fps(rw, size=(2560,2160), dtype=numpy.uint16, tester_class=QTimerFPSTester):
    rw.qt_object.fps_display_dock_widget.show()
    image = numpy.arange(size[0]*size[1], dtype=dtype).reshape(size, order='F')
    images = itertools.cycle([numpy.add(image, 255*i, dtype=dtype) for i in range(10)])
    tester = tester_class(images, rw)
    try:
        tester.start()
        rw.input('press enter end test')
    finally:
        tester.stop()
