from PyQt5.QtGui import QStandardItemModel, QStandardItem, QBrush, QIcon, QColor, QCursor, QPainter, QPolygonF
from PyQt5.QtWidgets import (QTreeView, QMenu, QApplication, QDialog, QVBoxLayout, QTextEdit,
                             QMessageBox, QHeaderView)
from PyQt5.QtCore import Qt, QModelIndex, QPointF, pyqtSignal

from core.test_tree import TestNode, build_test_tree
from core.failure_report import extract_failure_traceback
from gui_qt.status_icons import STATUS_PRIORITY, STATUS_COLORS, status_icon as _status_icon
from gui_qt.styles import styles
from gui_qt.styles.styles import console_style


# Longueur au-dela de laquelle un nom de lecteur est raccourci en en-tete de
# colonne. Le nom complet reste dans l'infobulle et sur la console.
MAX_READER_LABEL = 24


def short_reader_label(nom: str) -> str:
    """Nom court d'un lecteur, raccourci par MOTS entiers.

    Des lecteurs s'appellent `Infineon CryptoWrapperTU Reader` et
    `Infineon TestBiosWrapperTU Reader` : ce qui les distingue est au milieu.
    Couper a un nombre de caracteres donnait `apperTU Reader`, illisible et
    identique d'un lecteur a l'autre. On retire donc les mots de tete, un a un,
    jusqu'a tenir -- et si le dernier mot depasse a lui seul, on le garde
    entier plutot que de le mutiler.
    """
    nom = str(nom).strip()
    if len(nom) <= MAX_READER_LABEL:
        return nom

    mots = nom.split()
    for depart in range(1, len(mots)):
        court = " ".join(mots[depart:])
        if len(court) <= MAX_READER_LABEL:
            return court
    return mots[-1] if mots else nom


ID_ROLE = Qt.UserRole
NODEID_ROLE = Qt.UserRole + 1
STATUS_ROLE = Qt.UserRole + 2
KIND_ROLE = Qt.UserRole + 3
# Cible pytest du noeud (dossier, fichier, classe, fonction ou cas precis).
TARGET_ROLE = Qt.UserRole + 4


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
    # Emis (target, nodeid) quand un element est clique. `nodeid` est vide pour
    # les dossiers, fichiers et fonctions parametrees : seules les feuilles
    # executables en ont un.
    item_clicked = pyqtSignal(str, str)

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
        # Fonctions parametrees ayant recu un cas absent de la collecte initiale
        # pendant le run en cours. Leurs autres cas sont alors suspects : voir
        # prune_replaced_cases().
        self._functions_with_new_cases: list[QStandardItem] = []
        # Lecteurs du dernier run : une colonne de resultat chacun des qu'il
        # y en a plus d'un.
        self._readers: list[str] = []
        # Sortie console complete du dernier run, utilisee pour retrouver la trace
        # d'echec d'un test precis (menu contextuel "Voir la trace d'echec").
        self._last_output: str = ""

        self.model.itemChanged.connect(self._on_item_changed)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.clicked.connect(self._on_index_clicked)

    def _on_index_clicked(self, index: QModelIndex):
        item = self.model.itemFromIndex(index)
        if item is None:
            return
        self.item_clicked.emit(
            item.data(TARGET_ROLE) or "",
            item.data(NODEID_ROLE) or "",
        )

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
            self._functions_with_new_cases.clear()

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
        if node.target:
            item.setData(node.target, TARGET_ROLE)
        self._id_to_item[node.id] = item

        if node.nodeid:
            item.setData(node.nodeid, NODEID_ROLE)
            self._nodeid_to_item[self._norm(node.nodeid)] = item

        for child in node.children:
            item.appendRow(self._build_item(child))

        return item

    # -----------------------------
    # Ajout en cours de run
    # -----------------------------

    def add_nodeid(self, nodeid: str) -> QStandardItem | None:
        """Insere un test absent de l'arbre, en creant les niveaux manquants.

        Sert quand pytest execute un test que la collecte initiale ne connaissait
        pas. C'est le cas des jeux de tests dont les identifiants de parametres
        sont calcules a chaque collecte : l'arbre est etabli au chargement, pytest
        recollecte au lancement, et les nodeids different. Plutot que de perdre
        ces resultats, on complete l'arbre avec ce qui a reellement tourne.
        """
        # Le niveau de classe est conserve ici, et c'est _merge_node qui decide
        # de le garder ou non : lui seul voit comment l'arbre deja charge est
        # organise, alors qu'un nodeid isole ne le dit pas.
        racines = build_test_tree([nodeid], show_classes=True)
        if not racines:
            return None

        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            for racine in racines:
                self._merge_node(self.model.invisibleRootItem(), racine)
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.viewport().update()

        self._emit_selection_changed()
        return self._nodeid_to_item.get(self._norm(nodeid))

    def _has_class_children(self, parent_item: QStandardItem) -> bool:
        for row in range(parent_item.rowCount()):
            enfant = self._child_at(parent_item, row)
            if enfant is not None and enfant.data(KIND_ROLE) == "class":
                return True
        return False

    def _child_at(self, parent_item: QStandardItem, row: int) -> QStandardItem | None:
        """L'item racine ne repond pas a child() : il faut passer par le modele."""
        if parent_item is self.model.invisibleRootItem():
            return self.model.item(row)
        return parent_item.child(row)

    def _merge_node(self, parent_item: QStandardItem, node: TestNode):
        """Fusionne un noeud dans l'arbre existant, sans dupliquer les parents."""
        existant = None
        for row in range(parent_item.rowCount()):
            enfant = self._child_at(parent_item, row)
            if enfant is not None and enfant.text() == node.name \
                    and enfant.data(KIND_ROLE) == node.kind:
                existant = enfant
                break

        if existant is None and node.kind == "class" and not self._has_class_children(parent_item):
            # Ce fichier n'affiche pas ses classes : y ajouter ce niveau ferait
            # apparaitre la meme fonction deux fois, une fois sous sa classe et
            # une fois sans. Les tests remontent donc directement sous le fichier.
            for enfant_node in node.children:
                self._merge_node(parent_item, enfant_node)
            return

        if existant is None:
            # _build_item cree toute la chaine restante et l'enregistre.
            parent_item.appendRow(self._build_item(node))
            # Un cas ajoute sous une fonction parametree deja connue signifie que
            # la collecte du chargement ne decrivait pas les memes cas que le run.
            # Les cas restes de cette collecte-la sont donc perimes.
            if node.kind == "case" and parent_item.data(KIND_ROLE) == "function" \
                    and parent_item not in self._functions_with_new_cases:
                self._functions_with_new_cases.append(parent_item)
            return

        if node.nodeid and not existant.data(NODEID_ROLE):
            existant.setData(node.nodeid, NODEID_ROLE)
            self._nodeid_to_item[self._norm(node.nodeid)] = existant
        if node.target and not existant.data(TARGET_ROLE):
            existant.setData(node.target, TARGET_ROLE)

        for enfant_node in node.children:
            self._merge_node(existant, enfant_node)

    def start_run(self):
        """Ouvre un run : on repart sans cas en attente de remplacement."""
        self._functions_with_new_cases.clear()

    def prune_replaced_cases(self) -> int:
        """Retire les cas parametres laisses par une collecte perimee.

        Quand pytest recollecte au lancement et calcule d'autres identifiants de
        parametres (valeurs aleatoires, date, compteur), les cas etablis au
        chargement ne correspondent a rien : ils ne seront jamais executes sous
        ce nom. Les garder a cote des cas reellement executes donne un arbre deux
        fois trop long ou seule une minorite de lignes porte un resultat, ce qui
        se lit comme un arbre non mis a jour.

        On ne touche qu'aux fonctions parametrees ayant recu un cas inconnu
        pendant ce run, et seulement a leurs cas restes sans resultat : une
        selection partielle d'une fonction aux identifiants stables n'est jamais
        concernee, puisqu'elle ne cree aucun cas.

        Retourne le nombre de cas retires.
        """
        if not self._functions_with_new_cases:
            return 0

        supprimes = 0
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            for fonction in self._functions_with_new_cases:
                for row in range(fonction.rowCount() - 1, -1, -1):
                    enfant = fonction.child(row)
                    if enfant is None or enfant.data(KIND_ROLE) != "case":
                        continue
                    if enfant.data(STATUS_ROLE):
                        continue
                    nodeid = enfant.data(NODEID_ROLE)
                    if nodeid:
                        self._nodeid_to_item.pop(self._norm(nodeid), None)
                    self._id_to_item.pop(enfant.data(ID_ROLE), None)
                    fonction.removeRow(row)
                    supprimes += 1
                # Retirer des cas decoches peut rendre la fonction entierement
                # cochee : les cases des parents doivent suivre.
                if fonction.rowCount():
                    self._update_parents(fonction.child(0))
        finally:
            self._functions_with_new_cases.clear()
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.viewport().update()

        self._emit_selection_changed()
        return supprimes

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

    def get_selected_targets(self) -> list[str]:
        """Cibles pytest a lancer, en repliant les sous-arbres entierement coches.

        Passer un nodeid par test coute cher a pytest : il apparie chaque argument
        contre les items collectes. Mesure sur 6000 tests, l'execution passe de
        3,43 s en donnant les dossiers a 5,61 s en donnant les nodeids un a un.
        Quand tout un dossier ou tout un fichier est selectionne, on envoie donc
        son chemin, exactement comme on le ferait en ligne de commande.

        Un noeud partiellement coche est parcouru pour ne garder que ce qui est
        reellement selectionne : la selection reste au test pres.
        """
        targets: list[str] = []
        stack = [self.model.item(row) for row in range(self.model.rowCount() - 1, -1, -1)]

        while stack:
            item = stack.pop()
            state = item.checkState()
            if state == Qt.Unchecked:
                continue

            target = item.data(TARGET_ROLE)

            if state == Qt.Checked and target:
                targets.append(target)
                continue

            # Partiellement coche (ou sans cible) : on descend.
            for row in range(item.rowCount() - 1, -1, -1):
                stack.append(item.child(row))

        return targets

    def reset_result_colors(self):
        # Les signaux du modele sont bloques pendant tout le parcours. Sans ca,
        # chaque setData/setIcon/setFont emet itemChanged, donc _on_item_changed
        # repropage les cases a cocher sur tout l'arbre et recompte la selection :
        # un cout quadratique. Mesure sur 6000 tests : 45 s avec les signaux, 0,1 s
        # sans. Cette methode ne touche que l'apparence (statut, couleur, icone),
        # jamais les cases a cocher : rien ne depend de ces signaux ici.
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            stack = [self.model.item(row) for row in range(self.model.rowCount())]
            while stack:
                item = stack.pop()
                # Les colonnes de resultat aussi : un statut oublie ferait croire
                # a une divergence avec un lecteur qui n'a pas encore repondu.
                for colonne in range(self.model.columnCount()):
                    cellule = self._status_cell(item, colonne)
                    if cellule is None:
                        continue
                    cellule.setData(None, STATUS_ROLE)
                    cellule.setData(None, Qt.ForegroundRole)
                    cellule.setIcon(QIcon())
                    police = cellule.font()
                    police.setBold(False)
                    cellule.setFont(police)
                for row in range(item.rowCount()):
                    stack.append(item.child(row))
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.viewport().update()

    def drawBranches(self, painter, rect, index):
        """Dessine les fleches de deploiement nous-memes.

        Les fleches fournies par le style natif de Qt sont sombres et
        disparaissent sur le fond sombre de l'arbre. Les dessiner ici garantit
        qu'elles suivent la palette, quel que soit le theme.
        """
        palette = styles.palette()

        if self.selectionModel() is not None and self.selectionModel().isSelected(index):
            painter.fillRect(rect, QColor(palette["tree_selected"]))

        model = index.model()
        if model is None or not model.hasChildren(index):
            return

        sous_le_curseur = rect.contains(self.viewport().mapFromGlobal(QCursor.pos()))
        couleur = QColor(palette["branch_arrow_hover"] if sous_le_curseur
                         else palette["branch_arrow"])

        # La fleche occupe le dernier cran d'indentation, juste avant la case.
        centre_x = rect.right() - self.indentation() / 2 + 1
        centre_y = rect.center().y() + 1
        cote = 4.0

        if self.isExpanded(index):
            # Triangle vers le bas.
            points = [
                QPointF(centre_x - cote, centre_y - cote / 2),
                QPointF(centre_x + cote, centre_y - cote / 2),
                QPointF(centre_x, centre_y + cote * 0.9),
            ]
        else:
            # Triangle vers la droite.
            points = [
                QPointF(centre_x - cote / 2, centre_y - cote),
                QPointF(centre_x - cote / 2, centre_y + cote),
                QPointF(centre_x + cote * 0.9, centre_y),
            ]

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(couleur)
        painter.drawPolygon(QPolygonF(points))
        painter.restore()

    def recolor_statuses(self):
        """Reapplique les couleurs de statut avec la palette courante.

        Les couleurs sont posees sur les items au moment du resultat ; apres un
        changement de theme elles resteraient sinon dans l'ancienne palette. Le
        statut lui-meme est relu depuis STATUS_ROLE, donc rien n'est perdu.
        """
        self.setUpdatesEnabled(False)
        self.model.blockSignals(True)
        try:
            stack = [self.model.item(row) for row in range(self.model.rowCount())]
            while stack:
                item = stack.pop()
                status = item.data(STATUS_ROLE)
                if status:
                    self._apply_status(item, status)
                for row in range(item.rowCount()):
                    stack.append(item.child(row))
        finally:
            self.model.blockSignals(False)
            self.setUpdatesEnabled(True)
            self.viewport().update()

    # -----------------------------
    # Colonnes de resultat, une par lecteur
    # -----------------------------

    def set_readers(self, labels: list[str]):
        """Une colonne de resultat par lecteur, ou une seule colonne sans.

        Les tests sont les memes d'un lecteur a l'autre : les lister deux fois
        obligerait a balayer deux arbres pour comparer. Une ligne par test et une
        colonne par lecteur met la divergence sous les yeux.
        """
        self._readers = list(labels)
        colonnes = 1 + len(self._readers) if len(self._readers) > 1 else 1

        self.model.setColumnCount(colonnes)
        self.model.setHorizontalHeaderLabels(
            ["Tests"] + [short_reader_label(n) for n in self._readers[:colonnes - 1]])

        entete = self.header()
        # Le nom du test prend la place restante : un en-tete de lecteur ecrivait
        # sinon son nom complet en ecrasant la colonne qu'on vient lire.
        entete.setStretchLastSection(False)
        entete.setSectionResizeMode(0, QHeaderView.Stretch)

        for index in range(1, colonnes):
            entete.setSectionResizeMode(index, QHeaderView.ResizeToContents)
            cellule = self.model.horizontalHeaderItem(index)
            if cellule is not None:
                cellule.setToolTip(self._readers[index - 1])
                cellule.setForeground(QBrush(QColor(styles.reader_color(index - 1))))
                cellule.setTextAlignment(Qt.AlignCenter)
                # Un en-tete de lecteur nomme une colonne de coches : il n'a pas
                # a peser autant que les tests eux-memes. En petit et sans gras,
                # il rend a la colonne la largeur que son nom lui prenait.
                police = cellule.font()
                police.setPointSize(max(6, police.pointSize() - 2))
                police.setBold(False)
                cellule.setFont(police)

    def reader_column(self, reader_index: int) -> int:
        """Colonne portant le resultat de ce lecteur, 0 s'il n'y en a qu'un."""
        if len(getattr(self, "_readers", [])) > 1:
            return 1 + reader_index
        return 0

    def _status_cell(self, item: QStandardItem, colonne: int) -> QStandardItem | None:
        """Cellule de resultat de cette ligne, creee si besoin."""
        if colonne == 0:
            return item

        parent = item.parent()
        ligne = item.row()
        if parent is None:
            cellule = self.model.item(ligne, colonne)
            if cellule is None:
                cellule = QStandardItem()
                self.model.setItem(ligne, colonne, cellule)
        else:
            cellule = parent.child(ligne, colonne)
            if cellule is None:
                cellule = QStandardItem()
                parent.setChild(ligne, colonne, cellule)

        cellule.setEditable(False)
        cellule.setTextAlignment(Qt.AlignCenter)
        return cellule

    def divergent_nodeids(self) -> list[str]:
        """Tests dont les lecteurs ne rapportent pas le meme resultat."""
        if len(getattr(self, "_readers", [])) < 2:
            return []

        divergents = []
        for norm, item in self._nodeid_to_item.items():
            statuts = set()
            for index in range(len(self._readers)):
                cellule = self._status_cell(item, self.reader_column(index))
                statuts.add(cellule.data(STATUS_ROLE) if cellule is not None else None)
            if len(statuts) > 1:
                divergents.append(norm)
        return divergents

    def filter_divergences(self, actif: bool):
        """N'affiche que les tests sur lesquels les lecteurs ne s'accordent pas."""
        if not actif:
            self.clear_status_filter()
            return

        divergents = set(self.divergent_nodeids())
        root = self.model.invisibleRootItem()
        for row in range(root.rowCount()):
            self._filter_divergent(root.child(row), divergents)

    def _filter_divergent(self, item: QStandardItem, divergents: set) -> bool:
        nodeid = item.data(NODEID_ROLE)
        visible = bool(nodeid) and self._norm(nodeid) in divergents

        for row in range(item.rowCount()):
            if self._filter_divergent(item.child(row), divergents):
                visible = True

        self._set_row_hidden(item, not visible)
        return visible

    def update_single_test(self, nodeid: str, status: str, workspace: str = "",
                           create_missing: bool = False, reader_index: int = 0) -> bool:
        """Applique le statut au test correspondant.

        Retourne False si le test etait absent de l'arbre. Avec `create_missing`,
        il y est ajoute au passage : l'arbre reflete alors ce qui a reellement
        ete execute, plutot que de perdre le resultat.
        """
        item = self._find_item_for_nodeid(nodeid)
        connu = item is not None

        if item is None and create_missing:
            item = self.add_nodeid(nodeid)

        if item is None:
            return False

        # Meme raison que dans reset_result_colors, mais le cout est ici paye a
        # CHAQUE resultat de test recu : sans blocage, un run sur un gros
        # workspace ralentit a mesure que les resultats arrivent.
        colonne = self.reader_column(reader_index)
        self.model.blockSignals(True)
        try:
            cible = self._status_cell(item, colonne)
            self._apply_status(cible, status)
            if colonne == 0:
                self._propagate_status_to_parents(item)
            else:
                # Le nom du test porte le pire des lecteurs : une divergence se
                # repere sans deplier ni comparer les colonnes une a une.
                pire = self._worst_reader_status(item)
                if pire:
                    self._apply_status(item, pire)
                self._propagate_status_to_parents(item)
        finally:
            self.model.blockSignals(False)

        self.viewport().update()
        return connu

    def _worst_reader_status(self, item: QStandardItem) -> str | None:
        pire, priorite = None, 0
        for index in range(len(getattr(self, "_readers", []))):
            cellule = self._status_cell(item, self.reader_column(index))
            statut = cellule.data(STATUS_ROLE) if cellule is not None else None
            if STATUS_PRIORITY.get(statut, 0) > priorite:
                priorite = STATUS_PRIORITY.get(statut, 0)
                pire = statut
        return pire

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
            run_label = "Run this test"
        else:
            run_label = f"Run these {len(nodeids_under)} test(s)"
        run_action = menu.addAction(run_label)
        run_action.setEnabled(bool(nodeids_under))

        menu.addSeparator()

        copy_nodeid_action = menu.addAction("Copy nodeid")
        copy_nodeid_action.setEnabled(bool(own_nodeid))

        copy_path_action = menu.addAction("Copy file path")
        copy_path_action.setEnabled(bool(reference_nodeid))

        open_file_action = menu.addAction("Open source file")
        open_file_action.setEnabled(bool(reference_nodeid))

        open_log_action = menu.addAction("Open this test's log")
        open_log_action.setEnabled(bool(own_nodeid))

        own_status = item.data(STATUS_ROLE)
        menu.addSeparator()
        view_trace_action = menu.addAction("View failure traceback")
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
                "Traceback not found",
                "Could not find this test's failure traceback in the last run's output.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Failure traceback - {nodeid}")
        dialog.resize(800, 500)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(console_style())
        text_edit.setPlainText(trace)

        layout = QVBoxLayout(dialog)
        layout.addWidget(text_edit)
        dialog.exec_()
