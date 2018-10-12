# This code is licensed under the MIT License (see LICENSE file for details)

import threading
import itertools
import time
import numpy
from PyQt5 import Qt

from . import ris_widget

def test_fps(rw, size, dtype=numpy.uint16):
    rw.qt_object.fps_display_dock_widget.show()
    image = numpy.arange(size[0]*size[1], dtype=dtype).reshape(size, order='F')
    images = [numpy.add(image, 3*i, dtype=dtype) for i in range(10)]
    tester = FPSTester(images, rw)
    try:
        rw.input('press enter end test')
    finally:
        tester.running = False
        tester.join()

class FPSTester(threading.Thread):
    def __init__(self, images, rw):
        super().__init__(daemon=True)
        self.running = True
        self.images = itertools.cycle(images)
        self.rw = rw
        self.start()

    def run(self):
        while self.running:
            self.rw.image = next(self.images)
            interval = self.rw.qt_object.fps_display.last_interval
            if interval is None or interval > 0.1:
                interval = 1/20
            time.sleep(max(0, interval - 0.005))

def test_fps2(rw, size, dtype=numpy.uint16):
    rw.qt_object.fps_display_dock_widget.show()
    image = numpy.arange(size[0]*size[1], dtype=dtype).reshape(size, order='F')
    images = [numpy.add(image, 3*i, dtype=dtype) for i in range(10)]
    tester = FPSTester2(images, rw)
    try:
        rw.input('press enter end test')
    finally:
        tester.running = False
        tester.join()

class FPSReceiver(Qt.QObject):
    NEW_IMAGE_EVENT = Qt.QEvent.registerEventType()
    def __init__(self, images, rw):
        self.rw = rw
        self.images = itertools.cycle(images)
        super().__init__()

    def post(self):
        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.NEW_IMAGE_EVENT))

    def event(self, e):
        if e.type() == self.NEW_IMAGE_EVENT:
            self.rw.image = next(self.images)
            return True
        return super().event(e)

class FPSTester2(threading.Thread):
    def __init__(self, images, rw):
        super().__init__(daemon=True)
        self.running = True
        self.receiver = FPSReceiver(images, rw)
        self.rw = rw
        self.start()

    def run(self):
        while self.running:
            self.receiver.post()
            interval = self.rw.qt_object.fps_display.last_interval
            if interval is None or interval > 0.1:
                interval = 1/20
            time.sleep(max(0, interval - 0.005))


def test_fps3(rw, size, dtype=numpy.uint16):
    rw.qt_object.fps_display_dock_widget.show()
    image = numpy.arange(size[0]*size[1], dtype=dtype).reshape(size, order='F')
    images = [numpy.add(image, 3*i, dtype=dtype) for i in range(10)]
    images = itertools.cycle(images)
    def next_image():
        rw.image = next(images)
    t = Qt.QTimer()
    t.timeout.connect(next_image)
    t.start(1000/40)
    try:
        rw.input('press enter end test')
    finally:
        t.stop()


def test_fps4(rw, size, dtype=numpy.uint16):
    rw.qt_object.fps_display_dock_widget.show()
    image = numpy.arange(size[0]*size[1], dtype=dtype).reshape(size, order='F')
    images = [numpy.add(image, 3*i, dtype=dtype) for i in range(10)]
    images = itertools.cycle(images)
    while True:
        rw.image = next(images)
        rw.update()
        interval = rw.qt_object.fps_display.last_interval
        if interval is None or interval > 0.1:
            interval = 1/20
        time.sleep(max(0, interval - 0.005))
