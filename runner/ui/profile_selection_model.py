"""Distingue le bloc coche volontairement des parents coches par propagation."""
from PySide6.QtCore import Qt

from runner.ui.tree_model import TestTreeModel


class ProfileSelectionModel(TestTreeModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.explicit_branches = set()

    def set_tree(self, roots):
        self.explicit_branches.clear()
        super().set_tree(roots)

    def setData(self, index, value, role=Qt.CheckStateRole):
        if (not self.selection_locked and index.isValid() and index.column() == 0
                and role == Qt.CheckStateRole and index.internalPointer() not in self._blocked_rows):
            row = index.internalPointer()
            self.explicit_branches.difference_update(row.descendants())
            if row.children and Qt.CheckState(value) == Qt.Checked:
                self.explicit_branches.add(row)
            else:
                self.explicit_branches.discard(row)
        return super().setData(index, value, role)

    def set_all_checked(self, checked):
        if self.selection_locked:
            return
        self.explicit_branches = {row for row in self._roots if row.children} if checked else set()
        super().set_all_checked(checked)

    def set_checked_nodeids(self, nodeids):
        if self.selection_locked:
            return
        self.explicit_branches.clear()
        super().set_checked_nodeids(nodeids)
