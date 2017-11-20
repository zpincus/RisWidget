# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

class PropertyTableModel(Qt.QAbstractTableModel):
    """PropertyTableModel: Glue for making a Qt.TableView (or similar) in which the elements of a
    SignalingList are rows whose columns contain the values of the element properties specified in
    the property_names argument supplied to PropertyTableModel's constructor.

    On a per-element basis, PropertyTableModel attempts to connect to element."property_name"_changed
    signals.  If an element provides a _changed signal for a column's property, PropertyTableModel
    will connect to it and cause all associated views to update the appropriate cells when the that
    _changed signal is emitted.

    Additionally, "properties" may be plain attributes, with the limitation that changes to plain
    attributes will not be detected.

    An example of a widget containing an editable, drag-and-drop reorderable table containing
    the x, y, and z property values of a SignalingList's elements:

    from PyQt5 import Qt
    from ris_widget import qt_property
    from ris_widget.object_model import signaling_list, property_table_model, drag_drop_model_behavior

    class PosTableWidget(Qt.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.model = PosTableModel(('x', 'y', 'z'), signaling_list.SignalingList(), self)
            self.view = PosTableView(self.model, self)
            self.setLayout(Qt.QVBoxLayout())
            self.layout().addWidget(self.view)

        @property
        def positions(self):
            return self.model.signaling_list

        @positions.setter
        def positions(self, v):
            self.model.signaling_list = v

    class PosTableView(Qt.QTableView):
        def __init__(self, model, parent=None):
            super().__init__(parent)
            self.horizontalHeader().setSectionResizeMode(Qt.QHeaderView.ResizeToContents)
            self.setDragDropOverwriteMode(False)
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDragDropMode(Qt.QAbstractItemView.InternalMove)
            self.setDropIndicatorShown(True)
            self.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
            self.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
            self.delete_current_row_action = Qt.QAction(self)
            self.delete_current_row_action.setText('Delete current row')
            self.delete_current_row_action.triggered.connect(self._on_delete_current_row_action_triggered)
            self.delete_current_row_action.setShortcut(Qt.Qt.Key_Delete)
            self.delete_current_row_action.setShortcutContext(Qt.Qt.WidgetShortcut)
            self.addAction(self.delete_current_row_action)
            self.setModel(model)

        def _on_delete_current_row_action_triggered(self):
            sm = self.selectionModel()
            m = self.model()
            if None in (m, sm):
                return
            midx = sm.currentIndex()
            if midx.isValid():
                m.removeRow(midx.row())

    class PosTableModel(drag_drop_model_behavior.DragDropModelBehavior, property_table_model.PropertyTableModel):
        pass

    def float_or_none(v):
        if v is not None:
            return float(v)
        else:
            return None

    class Pos(qt_property.QtPropertyOwner):
        changed = Qt.pyqtSignal(object)

        def __init__(self, x=None, y=None, z=None, parent=None):
            super().__init__(parent)
            self.x, self.y, self.z = x, y, z

        x = qt_property.Property(
            default_value=None,
            coerce_arg_fn=float_or_none)

        y = qt_property.Property(
            default_value=None,
            coerce_arg_fn=float_or_none)

        z = qt_property.Property(
            default_value=None,
            coerce_arg_fn=float_or_none)
"""

    def __init__(self, property_names, signaling_list, allow_duplicates=False, parent=None):
        super().__init__(parent)
        self.property_names = list(property_names)
        self.property_columns = {pn : idx for idx, pn in enumerate(self.property_names)}
        assert all(map(lambda p: isinstance(p, str) and len(p) > 0, self.property_names)), 'property_names must be a non-empty iterable of non-empty strings.'
        if len(self.property_names) != len(set(self.property_names)):
            raise ValueError('The property_names argument contains at least one duplicate.')
        self._property_changed_slots = [lambda element, pn=pn: self._on_property_changed(element, pn) for pn in self.property_names]
        signaling_list.inserting.connect(self._on_inserting)
        signaling_list.inserted.connect(self._on_inserted)
        signaling_list.replaced.connect(self._on_replaced)
        signaling_list.removing.connect(self._on_removing)
        signaling_list.removed.connect(self._on_removed)
        self.signaling_list = signaling_list
        self.allow_duplicates = allow_duplicates
        self._attached = set()
        self.beginResetModel() # TODO: is this begin/end necessary?
        self._attach_elements(signaling_list)
        self.endResetModel()

    def rowCount(self, _=None):
        sl = self.signaling_list
        return 0 if sl is None else len(sl)

    def columnCount(self, _=None):
        return len(self.property_names)

    def flags(self, midx):
        f = Qt.Qt.ItemIsSelectable | Qt.Qt.ItemNeverHasChildren | self.drag_drop_flags(midx)
        if midx.isValid():
            f |= Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsEditable
        return f

    def drag_drop_flags(self, midx):
        return 0

    def get_cell(self, midx):
        return getattr(self.signaling_list[midx.row()], self.property_names[midx.column()])

    def data(self, midx, role=Qt.Qt.DisplayRole):
        if midx.isValid() and role in (Qt.Qt.DisplayRole, Qt.Qt.EditRole):
            return Qt.QVariant(self.get_cell(midx))
        return Qt.QVariant()

    def setData(self, midx, value, role=Qt.Qt.EditRole):
        if midx.isValid() and role == Qt.Qt.EditRole:
            setattr(self.signaling_list[midx.row()], self.property_names[midx.column()], value)
            return True
        return False

    def headerData(self, section, orientation, role=Qt.Qt.DisplayRole):
        if orientation == Qt.Qt.Vertical:
            if role == Qt.Qt.DisplayRole and 0 <= section < self.rowCount():
                return Qt.QVariant(section)
        elif orientation == Qt.Qt.Horizontal:
            if role == Qt.Qt.DisplayRole and 0 <= section < self.columnCount():
                return Qt.QVariant(self.property_names[section])
        return Qt.QVariant()

    def removeRows(self, row, count, parent=Qt.QModelIndex()):
        try:
            del self.signaling_list[row:row+count]
            return True
        except IndexError:
            return False

    def _attach_elements(self, elements):
        for element in elements:
            if element in self._attached:
                if self.allow_duplicates:
                    continue
                else:
                    raise RuntimeError('Duplicate item detected but not allowed in list')
            self._attached.add(element)
            for property_name, changed_slot in zip(self.property_names, self._property_changed_slots):
                try:
                    changed_signal = getattr(element, property_name + '_changed')
                    changed_signal.connect(changed_slot)
                except AttributeError:
                    pass

    def _detach_elements(self, elements):
        # must be called AFTER the relevant elements have already been removed from the signaling list:
        for element in elements:
            assert element in self._attached
            if self.allow_duplicates:
                if element in self.signaling_list:
                    # there's still another copy in the list
                    continue
            self._attached.remove(element)
            for property_name, changed_slot in zip(self.property_names, self._property_changed_slots):
                try:
                    changed_signal = getattr(element, property_name + '_changed')
                    changed_signal.disconnect(changed_slot)
                except AttributeError:
                    pass

    def _on_property_changed(self, element, property_name):
        column = self.property_columns[property_name]
        row = self.signaling_list.index(element)
        self.dataChanged.emit(self.createIndex(row, column), self.createIndex(row, column))

    def _on_inserting(self, idx, elements):
        self.beginInsertRows(Qt.QModelIndex(), idx, idx+len(elements)-1)

    def _on_inserted(self, idx, elements):
        self.endInsertRows()
        self._attach_elements(elements)
        self.dataChanged.emit(self.createIndex(idx, 0), self.createIndex(idx + len(elements) - 1, len(self.property_names) - 1))

    def _on_replaced(self, idxs, replaced_elements, elements):
        self._detach_elements(replaced_elements)
        self._attach_elements(elements)
        self.dataChanged.emit(self.createIndex(min(idxs), 0), self.createIndex(max(idxs), len(self.property_names) - 1))

    def _on_removing(self, idxs, elements):
        self.beginRemoveRows(Qt.QModelIndex(), min(idxs), max(idxs))

    def _on_removed(self, idxs, elements):
        self.endRemoveRows()
        self._detach_elements(elements)
