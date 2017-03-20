from PyQt5 import Qt

class ActionButton(Qt.QPushButton):
    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.updateButtonStatusFromAction()
        self.action.changed.connect(self.updateButtonStatusFromAction)
        self.clicked.connect(self.action.triggered)

    def updateButtonStatusFromAction(self):
        self.setText(self.action.text())
        self.setStatusTip(self.action.statusTip())
        self.setToolTip(self.action.toolTip())
        self.setIcon(self.action.icon())
        self.setEnabled(self.action.isEnabled())
        self.setCheckable(self.action.isCheckable())
        self.setChecked(self.action.isChecked())