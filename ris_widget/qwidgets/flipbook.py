# This code is licensed under the MIT License (see LICENSE file for details)


import numpy
import pathlib
import glob
from PyQt5 import Qt
import os.path

from ..object_model import uniform_signaling_list
from ..object_model import drag_drop_model_behavior
from ..object_model import property_table_model
from .. import image
from . import progress_thread_pool

try:
    import freeimage
except ModuleNotFoundError:
    freeimage = None

class ImageList(uniform_signaling_list.UniformSignalingList):
    def take_input_element(self, obj):
        return obj if isinstance(obj, image.Image) else image.Image(obj)

class PageList(uniform_signaling_list.UniformSignalingList):
    def take_input_element(self, obj):
        if isinstance(obj, ImageList):
            return obj
        if isinstance(obj, (numpy.ndarray, image.Image)):
            ret = ImageList((obj,))
            if hasattr(obj, 'name'):
                ret.name = obj.name
            return ret
        return ImageList(obj)

class _ReadPageTaskDoneEvent(Qt.QEvent):
    TYPE = Qt.QEvent.registerEventType()
    def __init__(self, task_page, error=False):
        super().__init__(self.TYPE)
        self.task_page = task_page
        self.error = error

class _ReadPageTaskPage:
    __slots__ = ["page", "im_fpaths", "im_names", "ims"]

_FLIPBOOK_PAGES_DOCSTRING = ("""
    The list of pages represented by a Flipbook instance's list view is available via a that
    Flipbook instance's .pages property.

    An individual page is itself a list of Images, but single Image pages need not be inserted
    as single element lists.  Single Image or array-like object insertions into the list of
    pages (.pages) are wrapped in an automatically created single element list if needed.
    Likewise, although a Flipbook instance's .pages property always and exclusively contains
    lists of pages, and pages, in turn, always and exclusively contain Image instances, 2D
    and 3D array-like objects (typically numpy.ndarray instances) inserted are always wrapped
    or copied into a new Image (an ndarray with appropriate striding and dtype is wrapped rather
    than copied).
    """)

class Flipbook(Qt.QWidget):
    """
    Flipbook: A Qt widget with a list view containing pages.  Calling a Flipbook instance's
    .add_image_files method is the easiest way in which to load a number of image files as pages
    into a Flipbook - see help(ris_widget.qwidgets.flipbook.Flipbook) for more information
    regarding this method.

    """

    __doc__ += _FLIPBOOK_PAGES_DOCSTRING

    current_page_changed = Qt.pyqtSignal(object)

    def __init__(self, layer_stack, parent=None):
        super().__init__(parent)
        self.layer_stack = layer_stack
        layout = Qt.QVBoxLayout()
        self.setLayout(layout)
        self.pages_view = PagesView()
        pages = PageList()
        self.pages_model = PagesModel(pages, self.pages_view)
        pages.replaced.connect(self._on_pages_replaced)
        self.pages_model.handle_dropped_files = self._handle_dropped_files
        self.pages_model.rowsInserted.connect(self._on_model_change)
        self.pages_model.rowsRemoved.connect(self._on_model_change)
        self.pages_model.modelReset.connect(self._on_model_change)
        self.pages_model.rowsInserted.connect(self._on_model_reset_or_rows_inserted_indirect, Qt.Qt.QueuedConnection)
        self.pages_model.modelReset.connect(self._on_model_reset_or_rows_inserted_indirect, Qt.Qt.QueuedConnection)
        self.pages_view.setModel(self.pages_model)
        self.pages_view.selectionModel().currentRowChanged.connect(self.apply)
        self.pages_view.selectionModel().selectionChanged.connect(self._on_page_selection_changed)
        layout.addWidget(self.pages_view)
        self._attached_page = None

        Qt.QShortcut(Qt.Qt.Key_Up, self, self.focus_prev_page)
        Qt.QShortcut(Qt.Qt.Key_Down, self, self.focus_next_page)

        mergebox = Qt.QHBoxLayout()
        self.merge_button = Qt.QPushButton('Merge pages')
        self.merge_button.clicked.connect(self.merge_selected)
        mergebox.addWidget(self.merge_button)
        self.delete_button = Qt.QPushButton('Delete pages')
        self.delete_button.clicked.connect(self.delete_selected)
        Qt.QShortcut(Qt.Qt.Key_Delete, self, self.delete_button.click, context=Qt.Qt.WidgetWithChildrenShortcut)
        Qt.QShortcut(Qt.Qt.Key_Backspace, self, self.delete_button.click, context=Qt.Qt.WidgetWithChildrenShortcut)
        mergebox.addWidget(self.delete_button)
        layout.addLayout(mergebox)

        playbox = Qt.QHBoxLayout()
        self.play_button = Qt.QPushButton('\N{BLACK RIGHT-POINTING POINTER}')
        self.play_button.setCheckable(True)
        self.play_button.setEnabled(False)
        self.play_button.toggled.connect(self._on_play_button_toggled)
        playbox.addSpacerItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Minimum))
        playbox.addWidget(self.play_button)
        self.fps_editor = Qt.QLineEdit()
        self.fps_editor.setValidator(Qt.QIntValidator(1, 99, parent=self))
        self.fps_editor.editingFinished.connect(self._on_fps_editing_finished)
        self.fps_editor.setFixedWidth(30)
        self.fps_editor.setAlignment(Qt.Qt.AlignCenter)

        playbox.addWidget(self.fps_editor)
        playbox.addWidget(Qt.QLabel('FPS'))
        playbox.addSpacerItem(Qt.QSpacerItem(0, 0, Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Minimum))
        layout.addLayout(playbox)
        self.playback_timer = Qt.QTimer()
        self.playback_timer.timeout.connect(self.advance_frame)
        self.playback_fps = 30

        self._on_page_selection_changed()
        self.apply()

    def apply(self):
        """Replace the image fields of the layers in .layer_stack with the images contained in the currently
        focused flipbook page, creating new layers as required, or clearing the image field of any excess
        layers. This method is called automatically when focus moves to a different page and when
        the contents of the current page change."""
        current_page_idx = self.current_page_idx
        if current_page_idx is None:
            self._detach_page()
            return
        pages = self.pages
        current_page = pages[current_page_idx]
        if current_page is not self._attached_page:
            self._detach_page()
            current_page.inserted.connect(self.apply)
            current_page.removed.connect(self.apply)
            current_page.replaced.connect(self.apply)
            self._attached_page = current_page
        self.layer_stack.layers = current_page # setter magic takes care of rest
        self.current_page_changed.emit(self)

    def _detach_page(self):
        if self._attached_page is not None:
            self._attached_page.inserted.disconnect(self.apply)
            self._attached_page.removed.disconnect(self.apply)
            self._attached_page.replaced.disconnect(self.apply)
            self._attached_page = None

    @staticmethod
    def _expand_to_path_list(path):
        if isinstance(path, str):
            if '?' in path or '*' in path:
                return list(map(pathlib.Path, glob.glob(path)))
            else:
                return [pathlib.Path(path)]
        elif isinstance(path, pathlib.Path):
            return [path]
        else:
            return list(path)

    def add_image_files(self, image_paths, page_names=None, image_names=None, insertion_point=None):
        """Add image files (or stacks of image files) to the flipbook.

        Parameters:
            image_paths: A single filename, a list containing filenames, or a list
                containing lists of filenames, where:
                    - a filename is either a pathlib.Path object or a string.
                    - a glob-string (i.e. contains wildcards * or ?) can be
                      provided anywhere a list of filenames is accepted.
            page_names: A list of the same length as image_paths, containing
                names for each entry to display in the flipbook. If not
                specified, the page names will be derived from the unique
                components of each entry image_paths.
            image_names: A list of same structure as image_paths, containing
                the desired image name for each loaded image. If not specified,
                the image name will be the full path to each image.
            insertion_point: numerical index before which to insert the images
                in the flipbook (negative values permitted). If not specified,
                images will be inserted after the last entry.

        Returns list of futures objects corresponding to the page-IO tasks.
        To wait until read is done, call concurrent.futures.wait() on this list.
        """
        if freeimage is None:
            raise RuntimeError('Could not import freeimage module for image IO')
        paths = []
        for page_paths in self._expand_to_path_list(image_paths):
            paths.append(list(map(pathlib.Path, self._expand_to_path_list(page_paths))))

        if page_names is None:
            abspaths = []
            flat_abspaths = []
            for subpaths in paths:
                abspaths.append([pp.resolve() for pp in subpaths])
                flat_abspaths.extend(abspaths[-1])
            if len(flat_abspaths) > 1:
                root = os.path.commonpath(flat_abspaths)
                page_names = [', '.join(str(p.relative_to(root)) for p in subpaths) for subpaths in abspaths]
            else:
                page_names = [paths[0][0].name]

        if image_names is None:
            image_names = [[str(p) for p in subpaths] for subpaths in paths]

        task_pages = []
        for file_paths, page_name, page_image_names in zip(paths, page_names, image_names):
            task_page = _ReadPageTaskPage()
            task_page.page = ImageList()
            task_page.page.name = page_name
            task_page.im_names = page_image_names
            task_page.im_fpaths = file_paths
            assert len(task_page.im_names) == len(task_page.im_fpaths)
            task_pages.append(task_page)

        if insertion_point is None:
            insertion_point = len(self.pages)
        return self.queue_page_creation_tasks(insertion_point, task_pages)


    def _handle_dropped_files(self, fpaths, dst_row, dst_column, dst_parent):
        if freeimage is None:
            return False
        if dst_row in (-1, None):
            dst_row = len(self.pages)
        self.add_image_files(fpaths, insertion_point=dst_row)
        if dst_row < len(self.pages):
            self.current_page_idx = dst_row
        return True

    def event(self, e):
        if e.type() == _ReadPageTaskDoneEvent.TYPE:
            if e.error:
                e.task_page.page.name += ' (ERROR)'
            else:
                for im, im_name in zip(e.task_page.ims, e.task_page.im_names):
                    e.task_page.page.append(image.Image(im, name=im_name))
            return True
        return super().event(e)

    def _read_page_task(self, task_page):
        task_page.ims = [freeimage.read(str(image_fpath)) for image_fpath in task_page.im_fpaths]
        Qt.QApplication.instance().postEvent(self, _ReadPageTaskDoneEvent(task_page))

    def _on_task_error(self, task_page):
        Qt.QApplication.instance().postEvent(self, _ReadPageTaskDoneEvent(task_page, error=True))

    def queue_page_creation_tasks(self, insertion_point, task_pages):
        if not hasattr(self, 'thread_pool'):
            self.thread_pool = progress_thread_pool.ProgressThreadPool(self.cancel_page_creation_tasks, self.layout)
        new_pages = []
        page_futures = []
        for task_page in task_pages:
            future = self.thread_pool.submit(self._read_page_task, task_page, on_error=self._on_task_error, on_error_args=(task_page,))
            task_page.page.on_removal = future.cancel
            new_pages.append(task_page.page)
            page_futures.append(future)
        self.pages[insertion_point:insertion_point] = new_pages
        self.ensure_page_focused()
        return page_futures

    def cancel_page_creation_tasks(self):
        for i, image_list in reversed(list(enumerate(self.pages))):
            if len(image_list) == 0:
                # page removal calls the on_removal function, which as above is the future's cancel()
                self.pages_model.removeRows(i, 1)

    def delete_selected(self):
        sm = self.pages_view.selectionModel()
        m = self.pages_model
        if sm is None or m is None:
            return
        selected_rows = self.selected_page_idxs[::-1]
        if len(selected_rows) == 0:
            return
        # "run" as in consecutive indexes specified as range rather than individually
        run_start_idx = selected_rows[0]
        run_length = 1
        for idx in selected_rows[1:]:
            if idx == run_start_idx - 1:
                # if the previous selected row is adjacent to the current "start"
                # of the run, extend the run one back
                run_start_idx = idx
                run_length += 1
            else:
                # delete one run and start recording the next
                m.removeRows(run_start_idx, run_length)
                run_start_idx = idx
                run_length = 1
        m.removeRows(run_start_idx, run_length)
        # re-select the next page after the deleted ones, or the prev page if that's all that's left
        pages_left = len(self.pages)
        if pages_left > 0:
            self.current_page_idx = min(run_start_idx, pages_left-1)

    def merge_selected(self):
        """The contents of the currently selected pages (by ascending index order in .pages
        and excluding the target page) are appended to the target page. The target page is
        the selected page with the lowest index."""
        mergeable_rows = list(self.selected_page_idxs)
        if len(mergeable_rows) < 2:
            return
        target_row = mergeable_rows.pop(0)
        target_page = self.pages[target_row]
        to_add = [self.pages[row] for row in mergeable_rows]
        midx = self.pages_model.createIndex(target_row, 0)
        self.pages_view.selectionModel().select(midx, Qt.QItemSelectionModel.Deselect)
        self.delete_selected()
        self.current_page_idx = None # clear remaining selection
        for image_list in to_add:
            target_page.extend(image_list)
        self.current_page_idx = target_row
        self.apply()

    def _on_page_selection_changed(self, newly_selected_midxs=None, newly_deselected_midxs=None):
        midxs = self.pages_view.selectionModel().selectedRows()
        self.delete_button.setEnabled(len(midxs) >= 1)
        self.merge_button.setEnabled(len(midxs) >= 2)

    def _on_pages_replaced(self, idxs, replaced_pages, pages):
        if self.current_page_idx in idxs:
            self.apply()

    def focus_prev_page(self):
        """Advance to the previous page, if there is one."""
        idx = self.current_page_idx
        if idx is None:
            selected_idxs = self.selected_page_idxs
            if not selected_idxs:
                self.ensure_page_focused()
                return
            idx = selected_idxs[0]
        self.current_page_idx = max(idx - 1, 0)

    def focus_next_page(self):
        """Advance to the next page, if there is one."""
        idx = self.current_page_idx
        if idx is None:
            selected_idxs = self.selected_page_idxs
            if not selected_idxs:
                self.ensure_page_focused()
                return
            idx = selected_idxs[0]
        self.current_page_idx = min(idx + 1, len(self.pages) - 1)

    @property
    def pages(self):
        return self.pages_model.signaling_list

    @pages.setter
    def pages(self, pages):
        if pages is not self.pages:
            #pages is self.pages when doing "self.pages += [...]", which translates into an iadd and then a set.
            # no need to replace with self...
            self.pages[:] = pages

    pages.__doc__ = _FLIPBOOK_PAGES_DOCSTRING

    @property
    def current_page_idx(self):
        midx = self.pages_view.selectionModel().currentIndex()
        if midx.isValid():
            return midx.row()

    @current_page_idx.setter
    def current_page_idx(self, idx):
        sm = self.pages_view.selectionModel()
        if idx is None:
            sm.clear()
        else:
            if not 0 <= idx < len(self.pages):
                raise IndexError('The value assigned to current_pages_idx must either be None or a value >= 0 and < page count.')
            midx = self.pages_model.index(idx, 0)
            sm.setCurrentIndex(midx, Qt.QItemSelectionModel.ClearAndSelect)

    @property
    def current_page(self):
        current_page_idx = self.current_page_idx
        if current_page_idx is not None:
            return self.pages[current_page_idx]

    @property
    def selected_page_idxs(self):
        return sorted(midx.row() for midx in self.pages_view.selectionModel().selectedRows() if midx.isValid())

    @selected_page_idxs.setter
    def selected_page_idxs(self, idxs):
        item_selection = Qt.QItemSelection()
        for idx in idxs:
            item_selection.append(Qt.QItemSelectionRange(self.pages_model.index(idx, 0)))
        sm = self.pages_view.selectionModel()
        sm.select(item_selection, Qt.QItemSelectionModel.ClearAndSelect)
        if idxs and self.current_page_idx not in idxs:
            sm.setCurrentIndex(self.pages_model.index(idxs[0], 0), Qt.QItemSelectionModel.Current)

    @property
    def selected_pages(self):
        return [self.pages[idx] for idx in self.selected_page_idxs]

    def ensure_page_focused(self):
        """If no page is selected:
           If there is a "current" page, IE highlighted but not selected, select it.
           If there is no "current" page, make .pages[0] current and select it."""
        sm = self.pages_view.selectionModel()
        if not sm.currentIndex().isValid():
            sm.setCurrentIndex(
                self.pages_model.index(0, 0),
                Qt.QItemSelectionModel.SelectCurrent | Qt.QItemSelectionModel.Rows)
        if len(sm.selectedRows()) == 0:
            sm.select(
                sm.currentIndex(),
                Qt.QItemSelectionModel.SelectCurrent | Qt.QItemSelectionModel.Rows)

    def _on_model_change(self):
        enable_play = len(self.pages) > 1
        self.play_button.setEnabled(enable_play)
        if not enable_play:
            self.play_button.setChecked(False)
        self.fps_editor.setEnabled(enable_play)

    def _on_model_reset_or_rows_inserted_indirect(self):
        self.pages_view.resizeRowsToContents()
        self.ensure_page_focused()

    @property
    def playback_fps(self):
        return 1000/self.playback_timer.interval()

    @playback_fps.setter
    def playback_fps(self, v):
        self.fps_editor.setText(str(v))
        interval_ms = (1/v)*1000
        self.playback_timer.setInterval(interval_ms)

    def _on_fps_editing_finished(self):
        self.playback_fps = int(self.fps_editor.text())

    def play(self):
        if self.play_button.isEnabled():
            self.play_button.setChecked(True)

    def pause(self):
        self.play_button.setChecked(False)


    def _on_play_button_toggled(self, v):
        if v:
            self.playback_timer.start()
        else:
            self.playback_timer.stop()

    def advance_frame(self):
        page_count = len(self.pages)
        if page_count == 0:
            return
        self.current_page_idx = (self.current_page_idx + 1) % page_count

class PagesView(Qt.QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
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

class ImageListListener(Qt.QObject):
    def __init__(self, image_list, pages_model, parent=None):
        super().__init__(parent)
        self.image_list = image_list
        self.pages_model = pages_model
        self.image_list.inserted.connect(self._on_change)
        self.image_list.replaced.connect(self._on_change)
        self.image_list.removed.connect(self._on_change)

    def remove(self):
        self.image_list.inserted.disconnect(self._on_change)
        self.image_list.replaced.disconnect(self._on_change)
        self.image_list.removed.disconnect(self._on_change)

    def _on_change(self, *args, **kws):
        idx = self.pages_model.signaling_list.index(self.image_list)
        index = self.pages_model.createIndex(idx, 0)
        self.pages_model.dataChanged.emit(index, index)

class PagesModel(drag_drop_model_behavior.DragDropModelBehavior, property_table_model.PropertyTableModel):
    def __init__(self, pages, parent=None):
        self.listeners = {}
        super().__init__(property_names=['name'], signaling_list=pages, parent=parent)
        self.modelAboutToBeReset.connect(self._on_model_about_to_be_reset)
        self.modelReset.connect(self._on_model_reset)

    def can_drop_rows(self, src_model, src_rows, dst_row, dst_column, dst_parent):
        return isinstance(src_model, PagesModel)

    def flags(self, midx):
        if midx.isValid() and midx.column() == 0:
            image_list = self.signaling_list[midx.row()]
            if len(image_list) == 0:
                return super().flags(midx) & ~Qt.Qt.ItemIsEditable
        return super().flags(midx)

    def data(self, midx, role=Qt.Qt.DisplayRole):
        if midx.isValid() and midx.column() == 0:
            image_list = self.signaling_list[midx.row()]
            if image_list is None:
                return Qt.QVariant()
            if len(image_list) == 0:
                if role == Qt.Qt.ForegroundRole:
                    return Qt.QVariant(Qt.QApplication.palette().brush(Qt.QPalette.Disabled, Qt.QPalette.WindowText))
        return super().data(midx, role)

    def removeRows(self, row, count, parent=Qt.QModelIndex()):
        try:
            to_remove = self.signaling_list[row:row+count]
        except IndexError:
            return False
        for row_entry in to_remove:
            # call on-removal callback if present
            on_removal = getattr(row_entry, 'on_removal', None)
            if on_removal:
                on_removal()
        return super().removeRows(row, count, parent)

    def _add_listeners(self, image_lists):
        for image_list in image_lists:
            self.listeners[image_list] = ImageListListener(image_list, self)

    def _remove_listeners(self, image_lists):
        for image_list in image_lists:
            listener = self.listeners.pop(image_list)
            listener.remove()

    def _on_inserted(self, idx, elements):
        super()._on_inserted(idx, elements)
        self._add_listeners(elements)

    def _on_replaced(self, idxs, replaced_elements, elements):
        super()._on_replaced(idxs, replaced_elements, elements)
        self._remove_listeners(replaced_elements)
        self._add_listeners(elements)

    def _on_removed(self, idxs, elements):
        super()._on_removed(idxs, elements)
        self._remove_listeners(elements)

    def _on_model_about_to_be_reset(self):
        self._remove_listeners(self.signaling_list)

    def _on_model_reset(self):
        self._add_listeners(self.signaling_list)
