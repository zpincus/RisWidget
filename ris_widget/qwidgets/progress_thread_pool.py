# This code is licensed under the MIT License (see LICENSE file for details)

import concurrent.futures as futures
import multiprocessing
import threading
import traceback

from PyQt5 import Qt


class UpdateEvent(Qt.QEvent):
    TYPE = Qt.QEvent.registerEventType()

    def __init__(self):
        super().__init__(self.TYPE)

    def post(self, receiver):
        Qt.QApplication.instance().postEvent(receiver, self)

class ProgressThreadPool(Qt.QWidget):
    def __init__(self, cancel_jobs, attached_layout, parent=None):
        super().__init__(parent)
        self.thread_pool = futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()-1)
        self.task_count_lock = threading.Lock()
        self._queued_tasks = 0
        self._retired_tasks = 0

        l = Qt.QHBoxLayout()
        self.setLayout(l)
        self._progress_bar = Qt.QProgressBar()
        self._progress_bar.setMinimum(0)
        l.addWidget(self._progress_bar)
        self._cancel_button = Qt.QPushButton('Cancel')
        l.addWidget(self._cancel_button)
        self._cancel_button.clicked.connect(cancel_jobs)
        attached_layout().addWidget(self)
        self.hide()

    def _task_done(self, future):
        self.increment_retired()
        try:
            future.result()
        except futures.CancelledError:
            pass
        except:
            if future.on_error is not None:
                future.on_error(*future.on_error_args)
            traceback.print_exc()
        finally:
            # clean up the future in case error args hold dangling references
            # (which they do in the flipbook image-loading use-case)
            del future.on_error
            del future.on_error_args

    def submit(self, task, *args, on_error=None, on_error_args=[], **kws):
        self.increment_queued()
        future = self.thread_pool.submit(task, *args, **kws)
        future.on_error = on_error
        future.on_error_args = on_error_args
        future.add_done_callback(self._task_done)
        return future

    def increment_queued(self):
        with self.task_count_lock:
            self._queued_tasks += 1
        UpdateEvent().post(self)

    def increment_retired(self):
        with self.task_count_lock:
            self._retired_tasks += 1
        UpdateEvent().post(self)

    def event(self, event):
        if event.type() == UpdateEvent.TYPE:
            self._update_progressbar()
            return True
        return super().event(event)

    def _update_progressbar(self):
        self._progress_bar.setMaximum(self._queued_tasks)
        self._progress_bar.setValue(self._retired_tasks)
        with self.task_count_lock:
            if self._queued_tasks == self._retired_tasks:
                self.hide()
                self._queued_tasks = 0
                self._retired_tasks = 0
            elif self.isHidden():
                self.show()

