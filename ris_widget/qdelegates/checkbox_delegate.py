# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt

class CheckboxDelegate(Qt.QStyledItemDelegate):
    """CheckboxDelegate: A light way of showing item-model-view cells containing boolean or tri-state-check values as a checkbox
    that is optionally interactive, well centered, and that does not have weird and deceptive appearances when contained within
    non-focused widgets.
    """
    def __init__(self, parent=None, margin=15):
        super().__init__(parent)
        self.style = Qt.QStyleFactory.create('fusion')
        self.cb_rect = self.style.subElementRect(Qt.QStyle.SE_CheckBoxIndicator, Qt.QStyleOptionButton())


    def paint(self, painter, option, midx):
        # Fill cell background in the *exact same manner* as the default delegate.  This is the simplest way to get the correct
        # cell background in all circumstances, including while dragging a row.
        self.style.drawPrimitive(Qt.QStyle.PE_PanelItemViewItem, option, painter, option.widget)
        if midx.isValid():
            flags = midx.flags()
            assert flags & Qt.Qt.ItemIsUserCheckable
            state = midx.data(Qt.Qt.CheckStateRole)
            assert state in {Qt.Qt.PartiallyChecked, Qt.Qt.Checked, Qt.Qt.Unchecked}
            checkbox = Qt.QStyleOptionButton()
            if state == Qt.Qt.Checked:
                checkbox.state |= Qt.QStyle.State_On
            elif state == Qt.Qt.PartiallyChecked:
                checkbox.state |= Qt.QStyle.State_NoChange
            else:
                checkbox.state |= Qt.QStyle.State_Off
            if flags & Qt.Qt.ItemIsEnabled:
                checkbox.state |= Qt.QStyle.State_Enabled
            else:
                checkbox.state |= Qt.QStyle.State_Disabled
            checkbox.rect = Qt.QRect(self.cb_rect)
            checkbox.rect.moveCenter(option.rect.center())
            self.style.drawControl(Qt.QStyle.CE_CheckBox, checkbox, painter)

    def sizeHint(self, option, midx):
        if midx.isValid():
            return self.cb_rect.size()
        return super().sizeHint(option, midx)

    def createEditor(self, parent, option, midx):
        # We don't make use of "edit mode".  Returning None here prevents double click, enter keypress, etc, from
        # engaging the default delegate behavior of dropping us into string edit mode, wherein a blinking text cursor
        # is displayed in the cell.
        return None

    def editorEvent(self, event, model, option, midx):
        flags = model.flags(midx)
        assert flags & Qt.Qt.ItemIsUserCheckable
        if not flags & Qt.Qt.ItemIsEnabled:
            return False

        if event.type() == Qt.QEvent.MouseButtonRelease:
            rect = Qt.QRect(self.cb_rect)
            rect.moveCenter(option.rect.center())
            if not rect.contains(event.pos()):
                return False
        elif event.type() == Qt.QEvent.KeyPress:
            if event.key() not in (Qt.Qt.Key_Space, Qt.Qt.Key_Select):
                return False
        else:
            return False

        state = midx.data(Qt.Qt.CheckStateRole)
        assert state in {Qt.Qt.PartiallyChecked, Qt.Qt.Checked, Qt.Qt.Unchecked}
        new_state = Qt.Qt.Unchecked if state == Qt.Qt.Checked else Qt.Qt.Checked
        return model.setData(midx, Qt.QVariant(new_state), Qt.Qt.CheckStateRole)
