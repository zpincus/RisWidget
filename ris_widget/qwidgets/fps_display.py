# This code is licensed under the MIT License (see LICENSE file for details)

import numpy
from PyQt5 import Qt
import time

class FPSDisplay(Qt.QWidget):
    """A widget displaying interval since last .notify call and 1 / the interval since last .notify call.
    FPSDisplay collects data and refreshes only when visible, reducing the cost of having it constructed
    and hidden with a signal attached to .notify."""
    def __init__(self, parent=None):
        super().__init__(parent)
        l = Qt.QGridLayout()
        self.setLayout(l)
        self.intervals = None
        self.fpss = None
        self._sample_count = None
        self.acquired_sample_count = 0
        self.prev_t = None
        r = 0
        self.sample_count_label = Qt.QLabel('Sample count: ')
        self.sample_count_spinbox = Qt.QSpinBox()
        self.sample_count_spinbox.setRange(2, 1024)
        self.sample_count_spinbox.valueChanged[int].connect(self._on_sample_count_spinbox_value_changed)
        l.addWidget(self.sample_count_label, r, 0, Qt.Qt.AlignRight)
        l.addWidget(self.sample_count_spinbox, r, 1)
        r += 1
        self.rate_label = Qt.QLabel('Framerate: ')
        self.rate_field = Qt.QLabel()
        self.rate_suffix_label = Qt.QLabel('fps')
        l.addWidget(self.rate_label, r, 0, Qt.Qt.AlignRight)
        l.addWidget(self.rate_field, r, 1, Qt.Qt.AlignRight)
        l.addWidget(self.rate_suffix_label, r, 2, Qt.Qt.AlignLeft)
        r += 1
        self.interval_label = Qt.QLabel('Interval: ')
        self.interval_field = Qt.QLabel()
        self.interval_suffix_label = Qt.QLabel()
        l.addWidget(self.interval_label, r, 0, Qt.Qt.AlignRight)
        l.addWidget(self.interval_field, r, 1, Qt.Qt.AlignRight)
        l.addWidget(self.interval_suffix_label, r, 2, Qt.Qt.AlignLeft)
        r += 1
        sp = Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding)
        l.addItem(Qt.QSpacerItem(0, 0, sp, r, 0, 1, -1)
        l.setColumnStretch(0, 0)
        l.setColumnStretch(1, 1)
        l.setColumnStretch(2, 0)
        self.sample_count = 20

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
            self.rate_field.setText('{:.2f}'.format(fps))
            if interval > 1:
                self.interval_field.setText('{:.2f}'.format(interval))
                self.interval_suffix_label.setText('s')
            else:
                self.interval_field.setText('{:.2f}'.format(interval * 1000))
                self.interval_suffix_label.setText('ms')

    def _on_sample_count_spinbox_value_changed(self, sample_count):
        self.sample_count = sample_count

    def hideEvent(self, event):
        super().hideEvent(event)
        self.clear()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()