from PyQt5.QtGui import QStandardItemModel, QStandardItem, QBrush, QIcon
from PyQt5.QtWidgets import QTreeView, QMenu, QApplication, QDialog, QVBoxLayout, QTextEdit, QMessageBox
from PyQt5.QtCore import Qt, QModelIndex, pyqtSignal

from core.test_tree import TestNode
from core.failure_report import extract_failure_traceback
from gui_qt.status_icons import STATUS_PRIORITY, STATUS_COLORS, status_icon as _status_icon
from gui_qt.styles.styles import console_style


ID_ROLE = Qt.UserRole
NODEID_ROLE = Qt.UserRole + 1
STATUS_ROLE = Qt.UserRole + 2
KIND_ROLE = Qt.UserRole + 3


class TestTreeView(QTreeView):
    __test__ = False  # Cette classe GUI n'est pas une classe de tests pytest.
    """
    Arbre Qt stable.

    Regle importante:
      - Qt identifie les items avec un UUID interne: ID_ROLE.
      - Le nodeid pytest est stocke separement: NODEID_ROLE.
      - Seules les feuilles executables ont un nodeid pytest.
    """

    # Emis avec la liste des nodeids executables a lancer (menu contextuel).
    run_requested = pyqtSignal(list)
    # Emis avec le chemin RELATIF (au workspace) du fichier a ouvrir.
    open_file_requested = pyqtSignal(str)
    # Emis avec le nodeid d'un test dont on veut ouvrir le fichier .log.
    open_log_requested = pyqtSignal(str)
    # Emis (nb coches, total) a chaque changement de selection des cases a cocher.
    selection_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Tests"])
        self.setModel(self.model)

        self.setUniformRowHeights(True)
        self.setExpandsOnDoubleClick(True)

        self._id_to_item: dict[str, QStandardItem] = {}
        self._nodeid_to_item: dict[str, QStandardItem] = {}
        self._updating = False
        # Sortie console complete du dernier run, utilisee pour retrouver la trace
        # d'echec d'un test precis (menu contextuel "Voir la trace d'echec").
        self._last_output: str = ""

        self.model.itemChanged.connect(self._on_item_changed)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _norm(self, value: str) -> str:
        return str(value).replace("\\", "/").strip()

    def set_last_output(self, text: str):
        """Memorise la sortie console du dernier run pour l'action 'Voir la trace d'echec'."""
        self._last_output = text or ""

    # -----------------------------
    # Loading
    # -----------------------------

    def load_tree(self, roots):
        """
        Charge l'arbre sans repasser ensuite sur tous les items.

        Sur les gros workspaces, l'ancien flux faisait:
          1) construire tout l'arbre
          2) refaire un set_all_checked(True) sur tout l'arbre

        Ce deuxieme passage peut provoquer un crash natif Qt sous Windows
        avec 0xC0000409 quand il y a beaucoup de tests/items.
        Maintenant chaque item est coche une seule fois au moment de sa creation,
        pendant que les signaux et les updates UI sont bloques.
        """
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            self.model.clear()
            self.model.setHorizontalHeaderLabels(["Tests"])
            self._id_to_item.clear()
            self._nodeid_to_item.clear()

            root_item = self.model.invisibleRootItem()
            for root in roots:
                root_item.appendRow(self._build_item(root))
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)

        # Ne pas deployer automatiquement les gros workspaces.
        # L utilisateur ouvre seulement les branches dont il a besoin.
        self.collapseAll()
        self.viewport().update()
        self._emit_selection_changed()

    def _build_item(self, node: TestNode) -> QStandardItem:
        item = QStandardItem(node.name)
        item.setCheckable(True)
        item.setAutoTristate(False)
        item.setTristate(bool(node.children))
        item.setEditable(False)
        item.setCheckState(Qt.Checked)

        item.setData(node.id, ID_ROLE)
        item.setData(node.kind, KIND_ROLE)
        self._id_to_item[node.id] = item

        if node.nodeid:
            item.setData(node.nodeid, NODEID_ROLE)
            self._nodeid_to_item[self._norm(node.nodeid)] = item

        for child in node.children:
            item.appendRow(self._build_item(child))

        return item

    # -----------------------------
    # Checkbox state management
    # -----------------------------

    def set_all_checked(self, checked: bool):
        """
        Coche ou decoche tout l'arbre sans changer la logique de selection.

        La version precedente testait les bons nodeids. On garde donc exactement
        le meme mecanisme de checkState, mais on coupe seulement les repaint Qt
        pendant la mise a jour de masse pour eviter la latence visuelle.
        """
        state = Qt.Checked if checked else Qt.Unchecked
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            for row in range(self.model.rowCount()):
                item = self.model.item(row)
                item.setCheckState(state)
                self._update_children(item, state)
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.viewport().update()
        self._emit_selection_changed()

    def _on_item_changed(self, item: QStandardItem):
        if self._updating:
            return

        self._updating = True
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            state = item.checkState()
            if item.rowCount() > 0 and state in (Qt.Checked, Qt.Unchecked):
                self._update_children(item, state)

            self._update_parents(item)
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self._updating = False
            self.viewport().update()
        self._emit_selection_changed()

    def _emit_selection_changed(self):
        total = len(self._nodeid_to_item)
        selected = sum(
            1 for item in self._nodeid_to_item.values()
            if item.checkState() == Qt.Checked
        )
        self.selection_changed.emit(selected, total)

    def _update_children(self, item: QStandardItem, state: Qt.CheckState):
        # Iteratif pour eviter les grosses recursions Qt/Python sur les gros workspaces.
        stack = [item.child(row) for row in range(item.rowCount())]
        while stack:
            child = stack.pop()
            child.setCheckState(state)
            for row in range(child.rowCount()):
                stack.append(child.child(row))

    def _update_parents(self, item: QStandardItem):
        parent = item.parent()
        while parent is not None:
            checked = 0
            unchecked = 0
            partial = 0

            for row in range(parent.rowCount()):
                state = parent.child(row).checkState()
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.Unchecked:
                    unchecked += 1
                else:
                    partial += 1

            if checked == parent.rowCount():
                parent.setCheckState(Qt.Checked)
            elif unchecked == parent.rowCount():
                parent.setCheckState(Qt.Unchecked)
            else:
                parent.setCheckState(Qt.PartiallyChecked)

            parent = parent.parent()

    # -----------------------------
    # Selection API
    # -----------------------------

    def get_selected_nodeids(self) -> list[str]:
        """
        Retourne uniquement les feuilles selectionnees.

        Version iterative: plus sure sur les gros arbres. La logique reste la meme:
        on lance uniquement les nodeids de feuilles cochees.
        """
        selected: list[str] = []
        stack = [self.model.item(row) for row in range(self.model.rowCount())]

        while stack:
            item = stack.pop()
            state = item.checkState()
            if state == Qt.Unchecked:
                continue

            nodeid = item.data(NODEID_ROLE)
            if nodeid and state == Qt.Checked:
                selected.append(nodeid)
                continue

            for row in range(item.rowCount() - 1, -1, -1):
                stack.append(item.child(row))

        return selected

    # -----------------------------
    # Results / coloring
    # -----------------------------

    def reset_result_colors(self):
        self.setUpdatesEnabled(False)
        try:
            stack = [self.model.item(row) for row in range(self.model.rowCount())]
            while stack:
                item = stack.pop()
                item.setData(None, STATUS_ROLE)
                item.setData(None, Qt.ForegroundRole)
                item.setIcon(QIcon())
                font = item.font()
                font.setBold(False)
                item.setFont(font)
                for row in range(item.rowCount()):
                    stack.append(item.child(row))
        finally:
            self.setUpdatesEnabled(True)
            self.viewport().update()

    def update_single_test(self, nodeid: str, status: str, workspace: str = ""):
        item = self._find_item_for_nodeid(nodeid)
        if item is None:
            return

        self._apply_status(item, status)
        self._propagate_status_to_parents(item)

    def color_tests(self, results: dict[str, str]):
        self.reset_result_colors()
        for nodeid, status in results.items():
            self.update_single_test(nodeid, status)

    def _find_item_for_nodeid(self, nodeid: str) -> QStandardItem | None:
        norm = self._norm(nodeid)

        item = self._nodeid_to_item.get(norm)
        if item is not None:
            return item

        # Fallback utile si pytest affiche parfois un prefixe different.
        matches = [item for key, item in self._nodeid_to_item.items()
                   if key.endswith(norm) or norm.endswith(key)]
        if len(matches) == 1:
            return matches[0]

        return None

    def _apply_status(self, item: QStandardItem, status: str):
        item.setData(status, STATUS_ROLE)
        color = STATUS_COLORS.get(status)
        if color:
            item.setForeground(QBrush(color))
        item.setIcon(_status_icon(status))

        font = item.font()
        font.setBold(status in ("FAILED", "ERROR"))
        item.setFont(font)

    def _propagate_status_to_parents(self, item: QStandardItem):
        parent = item.parent()
        while parent is not None:
            worst = self._worst_child_status(parent)
            if worst:
                self._apply_status(parent, worst)
            else:
                parent.setData(None, STATUS_ROLE)
                parent.setData(None, Qt.ForegroundRole)
                parent.setIcon(QIcon())
                font = parent.font()
                font.setBold(False)
                parent.setFont(font)
            parent = parent.parent()

    def _worst_child_status(self, item: QStandardItem) -> str | None:
        worst_status = None
        worst_priority = 0

        for row in range(item.rowCount()):
            child = item.child(row)
            status = child.data(STATUS_ROLE)
            priority = STATUS_PRIORITY.get(status, 0)
            if priority > worst_priority:
                worst_priority = priority
                worst_status = status

        return worst_status

    # -----------------------------
    # Status filter
    # -----------------------------

    def filter_by_status(self, status: str):
        target = status.upper()
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._filter_item(root.child(row), target)

    def filter_by_text(self, text: str):
        query = text.lower()
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._filter_item_by_text(root.child(row), query)

    def _filter_item_by_text(self, item: QStandardItem, query: str) -> bool:
        visible = query in item.text().lower()

        for row in range(item.rowCount()):
            child_visible = self._filter_item_by_text(item.child(row), query)
            visible = visible or child_visible

        self._set_row_hidden(item, not visible)
        return visible

    def clear_status_filter(self):
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._set_row_hidden(root.child(row), False)
            self._clear_filter_recursive(root.child(row))

    def _clear_filter_recursive(self, item: QStandardItem):
        for row in range(item.rowCount()):
            child = item.child(row)
            self._set_row_hidden(child, False)
            self._clear_filter_recursive(child)

    def _filter_item(self, item: QStandardItem, target: str) -> bool:
        visible = item.data(STATUS_ROLE) == target

        for row in range(item.rowCount()):
            child_visible = self._filter_item(item.child(row), target)
            visible = visible or child_visible

        self._set_row_hidden(item, not visible)
        return visible

    def _set_row_hidden(self, item: QStandardItem, hidden: bool):
        parent = item.parent()
        if parent is None:
            parent_index = QModelIndex()
        else:
            parent_index = parent.index()
        self.setRowHidden(item.row(), parent_index, hidden)

    # -----------------------------
    # Menu contextuel (clic-droit)
    # -----------------------------

    def _collect_nodeids(self, item: QStandardItem) -> list[str]:
        """Nodeids executables sous cet item (l'item lui-meme s'il est une feuille)."""
        nodeids: list[str] = []
        stack = [item]
        while stack:
            current = stack.pop()
            nodeid = current.data(NODEID_ROLE)
            if nodeid:
                nodeids.append(nodeid)
            for row in range(current.rowCount()):
                stack.append(current.child(row))
        return nodeids

    def _first_nodeid_under(self, item: QStandardItem) -> str | None:
        """Premier nodeid trouve sous cet item, utilise pour retrouver son fichier source."""
        stack = [item]
        while stack:
            current = stack.pop()
            nodeid = current.data(NODEID_ROLE)
            if nodeid:
                return nodeid
            for row in range(current.rowCount()):
                stack.append(current.child(row))
        return None

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return

        item = self.model.itemFromIndex(index)
        own_nodeid = item.data(NODEID_ROLE)
        nodeids_under = self._collect_nodeids(item)
        reference_nodeid = own_nodeid or self._first_nodeid_under(item)

        menu = QMenu(self)

        if own_nodeid:
            run_label = "Lancer ce test"
        else:
            run_label = f"Lancer ces {len(nodeids_under)} test(s)"
        run_action = menu.addAction(run_label)
        run_action.setEnabled(bool(nodeids_under))

        menu.addSeparator()

        copy_nodeid_action = menu.addAction("Copier le nodeid")
        copy_nodeid_action.setEnabled(bool(own_nodeid))

        copy_path_action = menu.addAction("Copier le chemin du fichier")
        copy_path_action.setEnabled(bool(reference_nodeid))

        open_file_action = menu.addAction("Ouvrir le fichier source")
        open_file_action.setEnabled(bool(reference_nodeid))

        open_log_action = menu.addAction("Ouvrir le log de ce test")
        open_log_action.setEnabled(bool(own_nodeid))

        own_status = item.data(STATUS_ROLE)
        menu.addSeparator()
        view_trace_action = menu.addAction("Voir la trace d'echec")
        view_trace_action.setEnabled(bool(own_nodeid) and own_status in ("FAILED", "ERROR"))

        chosen = menu.exec_(self.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if chosen is run_action:
            self.run_requested.emit(nodeids_under)
        elif chosen is copy_nodeid_action and own_nodeid:
            QApplication.clipboard().setText(own_nodeid)
        elif chosen is copy_path_action and reference_nodeid:
            QApplication.clipboard().setText(reference_nodeid.split("::")[0])
        elif chosen is open_file_action and reference_nodeid:
            self.open_file_requested.emit(reference_nodeid.split("::")[0])
        elif chosen is open_log_action and own_nodeid:
            self.open_log_requested.emit(own_nodeid)
        elif chosen is view_trace_action and own_nodeid:
            self._show_failure_trace(own_nodeid)

    def _show_failure_trace(self, nodeid: str):
        trace = extract_failure_traceback(self._last_output, nodeid)
        if not trace:
            QMessageBox.information(
                self,
                "Trace introuvable",
                "Impossible de retrouver la trace d'echec de ce test dans la sortie du dernier run.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Trace d'echec - {nodeid}")
        dialog.resize(800, 500)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(console_style())
        text_edit.setPlainText(trace)

        layout = QVBoxLayout(dialog)
        layout.addWidget(text_edit)
        dialog.exec_()
