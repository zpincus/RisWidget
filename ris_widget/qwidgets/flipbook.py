﻿# The MIT License (MIT)
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

import numpy
from pathlib import Path
from PyQt5 import Qt
from .. import om
from ..image import Image
from ..layer import Layer
from ..shared_resources import FREEIMAGE
from .progress_thread_pool import ProgressThreadPool, Task, TaskStatus

class ImageList(om.UniformSignalingList):
    def take_input_element(self, obj):
        return obj if isinstance(obj, Image) else Image(obj)

class PageList(om.UniformSignalingList):
    def take_input_element(self, obj):
        if isinstance(obj, (ImageList, Task)):
            return obj
        if isinstance(obj, (numpy.ndarray, Image)):
            obj = [obj]
        return ImageList(obj)

_X_THREAD_ADD_IMAGE_FILES_EVENT = Qt.QEvent.registerEventType()
_X_THREAD_ADD_IMAGE_FILE_STACKS = Qt.QEvent.registerEventType()

class _XThreadAddImageFilesEvent(Qt.QEvent):
    def __init__(self, image_fpaths):
        super().__init__(_X_THREAD_ADD_IMAGE_FILES_EVENT)
        self.image_fpaths = image_fpaths

class _XThreadAddImageFileStacksEvent(Qt.QEvent):
    def __init__(self, image_fpath_stacks):
        super().__init__(_X_THREAD_ADD_IMAGE_FILES_EVENT)
        self.image_fpath_stacks = image_fpath_stacks

#TODO: feed entirety of .pages to ProgressThreadPool and make ProgressThreadPool entirely ignore non-Task elements
#rather than raising exceptions
class Flipbook(Qt.QWidget):
    # TODO: update the following docstring
    """"""

    def __init__(self, layer_stack, parent=None):
        super().__init__(parent)
        self.layer_stack = layer_stack
        l = Qt.QVBoxLayout()
        self.setLayout(l)
        self.pages_model = PagesModel(PageList())
        self.pages_model.handle_dropped_files = self._handle_dropped_files
        self.pages_model.rowsInserted.connect(self._on_model_rows_inserted, Qt.Qt.QueuedConnection)
        self.pages_view = PagesView(self.pages_model)
        self.pages_view.setModel(self.pages_model)
        self.pages_view.selectionModel().currentRowChanged.connect(self._on_page_focus_changed)
        l.addWidget(self.pages_view)
        self.progress_thread_pool = None

    def add_image_files(self, image_fpaths):
        if Qt.QThread.currentThread() is Qt.QApplication.instance().thread():
            self._add_image_files(image_fpaths)
        else:
            Qt.QApplication.instance().postEvent(self, _XThreadAddImageFilesEvent(image_fpaths))

    def add_image_file_stacks(self, image_fpath_stacks):
        if Qt.QThread.currentThread() is Qt.QApplication.instance().thread():
            self._add_image_file_stacks(image_fpath_stacks)
        else:
            Qt.QApplication.instance().postEvent(self, _XThreadAddImageFileStacksEvent(image_fpath_stacks))

    def event(self, event):
        if event.type() == _X_THREAD_ADD_IMAGE_FILES_EVENT:
            assert isinstance(event, _XThreadAddImageFilesEvent)
            self._add_image_files(event.image_fpaths)
            return True
        if event.type() == _X_THREAD_ADD_IMAGE_FILE_STACKS:
            assert isinstance(event, _XThreadAddImageFileStacksEvent)
            self._add_image_file_stacks(event.image_fpath_stacks)
            return True
        return super().event(event)

    @property
    def pages(self):
        return self.pages_model.signaling_list

    @pages.setter
    def pages(self, pages):
        if not isinstance(pages, PageList):
            pages = PageList(pages)
        self.pages_model.signaling_list = pages
        self._on_page_focus_changed()

    @property
    def focused_page_idx(self):
        midx = self.pages_view.selectionModel().currentIndex()
        if midx.isValid():
            return midx.row()

    @property
    def focused_page(self):
        focused_page_idx = self.focused_page_idx
        if focused_page_idx is not None:
            return self.pages[focused_page_idx]

    def ensure_page_selected(self):
        """If no page is selected and .pages is not empty:
           If there is a "current" page, IE highlighted but not selected, select it.
           If there is no "current" page, make .pages[0] current and select it."""
        if not self.pages:
            return
        sm = self.pages_view.selectionModel()
        if not sm.currentIndex().isValid():
            sm.setCurrentIndex(
                    self.pages_model.index(0, 0),
                    Qt.QItemSelectionModel.SelectCurrent | Qt.QItemSelectionModel.Rows)
        if len(sm.selectedRows()) == 0:
            sm.select(
                sm.currentIndex(),
                Qt.QItemSelectionModel.SelectCurrent | Qt.QItemSelectionModel.Rows)

    def _on_model_rows_inserted(self, _, __, ___):
        self.pages_view.resizeRowsToContents()

    def _on_page_focus_changed(self, midx=None, old_midx=None):
        focused_page = self.focused_page
        if not isinstance(focused_page, ImageList):
            return
        layer_stack = self.layer_stack
        if layer_stack.layers is None:
            layer_stack.layers = []
        layers = layer_stack.layers
        lfp = len(focused_page)
        lls = len(layers)
        for idx in range(max(lfp, lls)):
            if idx >= lfp:
                layers[idx].image = None
            elif idx >= lls:
                layers.append(focused_page[idx])
            else:
                layers[idx].image = focused_page[idx]

    def _add_image_files(self, image_fpaths):
        irs = self._make_image_readers(image_fpaths)
        if irs is not None:
            self.pages.extend(irs)
            self.ensure_page_selected()

    def _add_image_file_stacks(self, image_fpath_stacks):
        isrs = self._make_image_stack_readers(image_fpath_stacks)
        if isrs is not None:
            self.pages.extend(isrs)
            self.ensure_page_selected()

    def _handle_dropped_files(self, fpaths, dst_row, dst_column, dst_parent):
        freeimage = FREEIMAGE(show_messagebox_on_error=True, error_messagebox_owner=None)
        if freeimage is None:
            return False
        self.pages[dst_row:dst_row] = self._make_image_readers(fpaths)
        self.ensure_page_selected()
        return True

    def _on_progress_thread_pool_task_status_changed(self, task, old_status):
        try:
            element_inst_count = self.pages_model._instance_counts[task]
        except KeyError:
            # We received queued notification informing us that something already removed from Tasks
            # changed to Completed status before being removed.
            return
        if task.status is TaskStatus.Completed:
            pages = self.pages
            name = task.result_name
            if isinstance(task.result, numpy.ndarray):
                image_stack = ImageList([Image(task.result, name=name)])
            else:
                image_stack = ImageList(Image(image_data, name=image_name) for image_data, image_name in task.result)
            image_stack.name = name
            task._progress_thread_pool = None
            next_idx = 0
            current_midx = self.pages_view.selectionModel().currentIndex()
            current_idx = current_midx.row() if current_midx.isValid() else None
            for _ in range(element_inst_count):
                idx = pages.index(task, next_idx)
                next_idx = idx + 1
                pages[idx] = image_stack
                if idx == current_idx:
                    self._on_page_focus_changed()
        else:
            next_idx = 0
            pages = self.pages
            m = self.pages_model
            for _ in range(element_inst_count):
                idx = pages.index(task, next_idx)
                next_idx = idx + 1
                m.dataChanged.emit(m.createIndex(idx, 0), m.createIndex(idx, 0))

    def _on_all_progress_thread_pool_tasks_retired(self):
        self.layout().removeWidget(self.progress_thread_pool)
        self.progress_thread_pool.deleteLater()
        self.progress_thread_pool = None

    def _make_image_readers(self, image_fpaths):
        assert Qt.QThread.currentThread() is Qt.QApplication.instance().thread()
        freeimage = FREEIMAGE(show_messagebox_on_error=True, error_messagebox_owner=self)
        if freeimage:
            if self.progress_thread_pool is None:
                self.progress_thread_pool = ProgressThreadPool()
                self.progress_thread_pool.task_status_changed.connect(self._on_progress_thread_pool_task_status_changed)
                self.progress_thread_pool.all_tasks_retired.connect(self._on_all_progress_thread_pool_tasks_retired)
                self.layout().addWidget(self.progress_thread_pool)
            readers = []
            for fpath in image_fpaths:
                reader = self.progress_thread_pool.submit(freeimage.read, str(fpath))
                reader.result_name = str(fpath)
                readers.append(reader)
            return readers

    def _make_image_stack_readers(self, image_fpath_stacks):
        assert Qt.QThread.currentThread() is Qt.QApplication.instance().thread()
        freeimage = FREEIMAGE(show_messagebox_on_error=True, error_messagebox_owner=self)
        if freeimage:
            if self.progress_thread_pool is None:
                self.progress_thread_pool = ProgressThreadPool()
                self.progress_thread_pool.task_status_changed.connect(self._on_progress_thread_pool_task_status_changed)
                self.progress_thread_pool.all_tasks_retired.connect(self._on_all_progress_thread_pool_tasks_retired)
                self.layout().addWidget(self.progress_thread_pool)
            stack_readers = []
            def read_stack(image_fpaths):
                return [(freeimage.read(str(image_fpath)), str(image_fpath)) for image_fpath in image_fpaths]
            for image_fpaths in image_fpath_stacks:
                stack_reader = self.progress_thread_pool.submit(read_stack, image_fpaths)
                stack_reader.result_name = ', '.join(Path(image_fpath).stem for image_fpath in image_fpaths)
                stack_readers.append(stack_reader)
            return stack_readers

@om.item_view_shortcuts.with_selected_rows_deletion_shortcut
class PagesView(Qt.QTableView):
    def __init__(self, pages_model, parent=None):
        super().__init__(parent)
        self.setModel(pages_model)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionsClickable(False)
        self.verticalHeader().setHighlightSections(False)
        self.verticalHeader().setSectionsClickable(False)
        self.setTextElideMode(Qt.Qt.ElideLeft)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(Qt.QAbstractItemView.DragDrop)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.Qt.LinkAction)
        self.horizontalHeader().setSectionResizeMode(Qt.QHeaderView.ResizeToContents)
        self.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
        self.setSelectionMode(Qt.QAbstractItemView.ExtendedSelection)
        self.setWordWrap(False)

class PagesModelDragDropBehavior(om.signaling_list.DragDropModelBehavior):
    def can_drop_rows(self, src_model, src_rows, dst_row, dst_column, dst_parent):
        return isinstance(src_model, PagesModel)

class PagesModel(PagesModelDragDropBehavior, om.signaling_list.PropertyTableModel):
    PROPERTIES = (
        'name',
        )

    def __init__(self, signaling_list=None, parent=None):
        super().__init__(self.PROPERTIES, signaling_list, parent)

    def flags(self, midx):
        if midx.isValid() and midx.column() == self.PROPERTIES.index('name'):
            element = self.signaling_list[midx.row()]
            if isinstance(element, Task):
                return super().flags(midx) & ~Qt.Qt.ItemIsEditable
        return super().flags(midx)

    def data(self, midx, role=Qt.Qt.DisplayRole):
        if midx.isValid() and midx.column() == self.PROPERTIES.index('name'):
            element = self.signaling_list[midx.row()]
            if isinstance(element, map):
                pass
            if element is None:
                return Qt.QVariant()
            if isinstance(element, Task):
                if role == Qt.Qt.DisplayRole:
                    return Qt.QVariant('{} ({})'.format(element.result_name, element.status.name))
                if role == Qt.Qt.ForegroundRole:
                    return Qt.QVariant(Qt.QApplication.palette().brush(Qt.QPalette.Disabled, Qt.QPalette.WindowText))
        return super().data(midx, role)
