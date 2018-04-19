# This code is licensed under the MIT License (see LICENSE file for details)

import numpy
from PyQt5 import Qt
import time

class FPSDisplay(Qt.QWidget):
    """A widget displaying interval since last .notify call and 1 / the interval since last .notify call.
    FPSDisplay collects data and refreshes only when visible, reducing the cost of having it constructed
    and hidden with a signal attached to .notify."""
    def __init__(self, changed_signal, parent=None):
        super().__init__(parent)
        l = Qt.QFormLayout()
        self.setLayout(l)
        self.intervals = None
        self.fpss = None
        self._sample_count = None
        self.acquired_sample_count = 0
        self.prev_t = None
        self.sample_count_spinbox = Qt.QSpinBox()
        self.sample_count_spinbox.setRange(2, 1024)
        self.sample_count_spinbox.valueChanged[int].connect(self._on_sample_count_spinbox_value_changed)
        l.addRow('Sample count:', self.sample_count_spinbox)
        fps_box = Qt.QHBoxLayout()
        fps_box.setSpacing(3)
        l.addRow(fps_box)
        self.rate_field = Qt.QLabel()
        self.rate_field.setFont(Qt.QFont('Courier'))
        rate_suffix = Qt.QLabel('fps')
        fps_box.addWidget(self.rate_field, alignment=Qt.Qt.AlignRight)
        fps_box.addWidget(rate_suffix, alignment=Qt.Qt.AlignLeft)
        fps_box.addSpacing(12)
        self.interval_field = Qt.QLabel()
        self.interval_field.setFont(Qt.QFont('Courier'))
        self.interval_suffix = Qt.QLabel()
        fps_box.addWidget(self.interval_field, alignment=Qt.Qt.AlignRight)
        fps_box.addWidget(self.interval_suffix, alignment=Qt.Qt.AlignLeft)

        self.sample_count = 60
        changed_signal.connect(self.notify)

    @property
    def sample_count(self):
        return self._sample_count

    @sample_count.setter
    def sample_count(self, v):
        assert 2 <= v <= 1024
        if v != self._sample_count:
            self._sample_count = v
            self.intervals = numpy.empty((self._sample_count - 1,), dtype=numpy.float64)
            self.fpss = numpy.empty((self._sample_count - 1,), dtype=numpy.float64)
            self.sample_count_spinbox.setValue(self.sample_count)
            self.clear()

    def notify(self):
        if not self.isVisible():
            return
        t = time.time()
        if self.prev_t is None:
            self.prev_t = t
            self.acquired_sample_count += 1
        else:
            i = (self.acquired_sample_count-1) % self.intervals.shape[0]
            self.intervals[i] = v = t - self.prev_t
            self.fpss[i] = 0 if v == 0 else 1 / v
            self.acquired_sample_count += 1
            self.prev_t = t
            self._refresh()

    def clear(self):
        self.acquired_sample_count = 0
        self.prev_t = None
        if self.isVisible():
            self._refresh()

    def _refresh(self):
        if self.acquired_sample_count < 2:
            self.rate_field.setText('')
            self.interval_field.setText('')
        else:
            end = min(self._sample_count, self.acquired_sample_count - 1)
            intervals = self.intervals[:end]
            interval = intervals.mean()
            fpss = self.fpss[:end]
            fps = fpss.mean()
            self.rate_field.setText('{:.1f}'.format(round(fps, 1)))
            if interval > 1:
                self.interval_suffix.setText('s/frame')
            else:
                interval *= 1000
                self.interval_suffix.setText('ms/frame')
            self.interval_field.setText('{:.1f}'.format(round(interval, 1)))

    def _on_sample_count_spinbox_value_changed(self, sample_count):
        self.sample_count = sample_count

    def hideEvent(self, event):
        super().hideEvent(event)
        self.clear()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()