"""Modele Qt de l'arbre des tests : une colonne de statut par lecteur.

Un QTreeWidget rempli item par item recopie les donnees dans des widgets : sur
plusieurs milliers de tests, chaque mise a jour coute cher et l'etat se dedouble
entre le modele metier et l'affichage. Ici le modele EST la source, la vue n'en
dessine que la partie visible.
"""

from __future__ import annotations

from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtGui import QColor

from runner.domain.models import Kind, Reader, Status, TestNode, worst
from runner.ui import icons
from runner.ui import tokens as t

# Roles propres a ce modele, au-dela de ceux de Qt.
NODE_ROLE = Qt.UserRole + 1
NODEID_ROLE = Qt.UserRole + 2


class _Row:
    """Un noeud de l'arbre, plus ce que l'affichage doit retenir de lui.

    Le parent est garde pour remonter : Qt demande l'index du parent a chaque
    fois qu'il descend, et le retrouver en parcourant l'arbre couterait un
    balayage complet par appel.
    """

    __slots__ = ("node", "parent", "children", "row", "checked", "statuses", "agg")

    def __init__(self, node: TestNode, parent: "_Row | None", row: int):
        self.node = node
        self.parent = parent
        self.row = row
        self.checked = True
        # Statut par index de lecteur, pour les feuilles seulement : celui d'un
        # regroupement se deduit de ses enfants (voir status_for).
        self.statuses: dict[int, Status] = {}
        # Statut agrege d'un regroupement, par lecteur, retenu apres calcul.
        # Sans lui, chaque redessin refaisait le parcours de tout le sous-arbre
        # -- sur un dossier replie de 2000 tests, 2000 visites par colonne et
        # par image, pour une valeur qui n'avait pas bouge.
        self.agg: dict[int, Status] = {}
        self.children: list[_Row] = [
            _Row(enfant, self, position)
            for position, enfant in enumerate(node.children)
        ]

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def descendants(self):
        for enfant in self.children:
            yield enfant
            yield from enfant.descendants()

    def leaves(self):
        if self.is_leaf:
            if self.node.nodeid:
                yield self
            return
        for enfant in self.children:
            yield from enfant.leaves()


class TestTreeModel(QAbstractItemModel):
    # Le nom commence par "Test" : sans cela pytest tenterait de le collecter
    # comme une classe de tests et emettrait un avertissement a chaque run.
    __test__ = False

    """Arbre des tests, coche par coche, avec un statut par lecteur.

    Utilisable sans fenetre : les tests du modele l'instancient seul et lisent
    ses donnees par `index()` / `data()`.
    """

    selection_changed = pyqtSignal(int, int)  # coches, total

    def __init__(self, parent=None):
        super().__init__(parent)
        self._roots: list[_Row] = []
        self._by_nodeid: dict[str, _Row] = {}
        self._search_index: tuple[tuple[str, str], ...] = ()
        self._readers: tuple[Reader, ...] = ()
        # Decompte par statut des cases (test, lecteur) deja rendues. Tenu au
        # fil de l'eau : le recalculer a chaque resultat reparcourrait tout
        # l'arbre, ce qui redonnerait le gel quadratique deja corrige.
        self._tally: dict[Status, int] = {}
        # Le nodeid stress-teste, et le texte court a coller sur sa ligne --
        # voir `set_stress_annotation`.
        self._stress_annotation: tuple[str, str] | None = None

    # ------------------------------------------------------------- chargement

    def set_tree(self, roots: list[TestNode]) -> None:
        self.beginResetModel()
        self._roots = [_Row(n, None, i) for i, n in enumerate(roots)]
        self._by_nodeid = {}
        for racine in self._roots:
            for ligne in [racine, *racine.descendants()]:
                if ligne.node.nodeid:
                    self._by_nodeid[ligne.node.nodeid] = ligne
        # `casefold()` n'est fait qu'a la collecte, pas a chaque caractere
        # saisi dans la recherche. Sur plusieurs milliers de parametres, ces
        # allocations repetees etaient visibles dans le fil de l'interface.
        self._search_index = tuple(
            (nodeid, nodeid.casefold()) for nodeid in self._by_nodeid)
        self.endResetModel()
        self._emit_selection()

    def set_readers(self, readers: tuple[Reader, ...]) -> None:
        """Une colonne de statut par lecteur, ou une seule sans lecteur."""
        self.beginResetModel()
        self._readers = tuple(readers)
        # Pas de purge des agregats ici : ils sont ranges par index de lecteur,
        # exactement comme les statuts des feuilles dont ils derivent. Les deux
        # vieillissent donc ensemble et restent coherents. Ce qui repart
        # vraiment de zero, c'est `set_tree` -- il reconstruit les lignes -- et
        # `clear_statuses`, qui vide les deux.
        self.endResetModel()

    @property
    def readers(self) -> tuple[Reader, ...]:
        return self._readers

    def matching_nodeids(self, query: str) -> list[str]:
        """Nodeids contenant ``query``, dans l'ordre stable de l'arbre."""
        cherche = query.strip().casefold()
        if not cherche:
            return []
        return [nodeid for nodeid, normalise in self._search_index
                if cherche in normalise]

    # ------------------------------------------------------ interface Qt

    def columnCount(self, parent=QModelIndex()) -> int:
        return 1 + max(1, len(self._readers))

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return len(self._roots)
        return len(parent.internalPointer().children)

    def index(self, row: int, column: int, parent=QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        enfants = self._roots if not parent.isValid() else parent.internalPointer().children
        return self.createIndex(row, column, enfants[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        parent = index.internalPointer().parent
        if parent is None:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            if section == 0:
                return "Test"
            if section - 1 < len(self._readers):
                return self._readers[section - 1].short_name
            return "Status"
        if role == Qt.ToolTipRole and 0 < section <= len(self._readers):
            return self._readers[section - 1].name
        if role == Qt.ForegroundRole and 0 < section <= len(self._readers):
            return QColor(t.reader_color(self._readers[section - 1].index))
        if role == Qt.TextAlignmentRole and section > 0:
            return int(Qt.AlignCenter)
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        drapeaux = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            drapeaux |= Qt.ItemIsUserCheckable
        return drapeaux

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        ligne: _Row = index.internalPointer()

        if index.column() == 0:
            return self._data_colonne_nom(ligne, role)
        return self._data_colonne_statut(ligne, index.column() - 1, role)

    def _data_colonne_nom(self, ligne: _Row, role):
        annotee = (self._stress_annotation is not None
                  and ligne.node.nodeid == self._stress_annotation[0])
        if role == Qt.DisplayRole:
            if annotee:
                return f"{ligne.node.name}   {self._stress_annotation[1]}"
            return ligne.node.name
        if role == Qt.CheckStateRole:
            return self._check_state(ligne)
        if role == Qt.DecorationRole:
            return icons.kind_icon(ligne.node.kind)
        if role == NODE_ROLE:
            return ligne.node
        if role == NODEID_ROLE:
            return ligne.node.nodeid
        if role == Qt.ToolTipRole:
            if annotee:
                return f"{ligne.node.nodeid or ligne.node.name} — {self._stress_annotation[1]}"
            return ligne.node.nodeid or ligne.node.name
        if role == Qt.ForegroundRole:
            from PyQt5.QtGui import QColor

            if annotee:
                return QColor(t.ACCENT)
            if ligne.node.kind is Kind.FOLDER:
                return QColor(t.TEXT_MUTED)
        return None

    def set_stress_annotation(self, nodeid: str, texte: str) -> None:
        """Colle `texte` a la suite du nom de `nodeid`, dans l'arbre.

        Le badge vit sur la ligne du test qu'on stresse, la ou on a clique
        "Run N times" pour le lancer -- pas dans un widget a part, ailleurs
        dans la fenetre, qu'il faut associer mentalement au bon test.
        """
        self._stress_annotation = (nodeid, texte)
        self._repeindre_annotation(nodeid)

    def clear_stress_annotation(self) -> None:
        if self._stress_annotation is None:
            return
        nodeid = self._stress_annotation[0]
        self._stress_annotation = None
        self._repeindre_annotation(nodeid)

    def _repeindre_annotation(self, nodeid: str) -> None:
        ligne = self._by_nodeid.get(nodeid)
        if ligne is None:
            return
        index = self.createIndex(ligne.row, 0, ligne)
        self.dataChanged.emit(
            index, index, [Qt.DisplayRole, Qt.ForegroundRole, Qt.ToolTipRole])

    def _data_colonne_statut(self, ligne: _Row, reader_index: int, role):
        statut = self.status_for(ligne, reader_index)
        if role == Qt.DecorationRole and statut is not Status.PENDING:
            return icons.status_icon(statut, group=not ligne.is_leaf)
        if role == Qt.ToolTipRole and statut is not Status.PENDING:
            return statut.label
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        return None

    def setData(self, index: QModelIndex, value, role=Qt.CheckStateRole) -> bool:
        if not index.isValid() or role != Qt.CheckStateRole or index.column() != 0:
            return False

        ligne: _Row = index.internalPointer()
        coche = value == Qt.Checked
        self._set_checked(ligne, coche)
        self._emit_selection()
        return True

    # ------------------------------------------------------------- selection

    def _check_state(self, ligne: _Row):
        if ligne.is_leaf:
            return Qt.Checked if ligne.checked else Qt.Unchecked
        etats = {self._check_state(e) for e in ligne.children}
        if etats == {Qt.Checked}:
            return Qt.Checked
        if etats == {Qt.Unchecked}:
            return Qt.Unchecked
        return Qt.PartiallyChecked

    def _set_checked(self, ligne: _Row, coche: bool) -> None:
        """Coche le noeud et toute sa descendance, puis rafraichit ses parents.

        Cocher un dossier coche ce qu'il contient : l'utilisateur pense en
        blocs, pas en feuilles.
        """
        ligne.checked = coche
        for descendant in ligne.descendants():
            descendant.checked = coche

        haut = self.createIndex(ligne.row, 0, ligne)
        self.dataChanged.emit(haut, self.createIndex(ligne.row, 0, ligne),
                              [Qt.CheckStateRole])
        self._rafraichir_branche(ligne)

        parent = ligne.parent
        while parent is not None:
            index_parent = self.createIndex(parent.row, 0, parent)
            self.dataChanged.emit(index_parent, index_parent, [Qt.CheckStateRole])
            parent = parent.parent

    def _rafraichir_branche(self, ligne: _Row) -> None:
        if not ligne.children:
            return
        premier = self.createIndex(0, 0, ligne.children[0])
        dernier = self.createIndex(len(ligne.children) - 1, 0, ligne.children[-1])
        self.dataChanged.emit(premier, dernier, [Qt.CheckStateRole])
        for enfant in ligne.children:
            self._rafraichir_branche(enfant)

    def set_all_checked(self, coche: bool) -> None:
        for racine in self._roots:
            self._set_checked(racine, coche)
        self._emit_selection()

    def set_checked_nodeids(self, nodeids) -> None:
        """Coche exactement ces nodeids -- et eux seuls -- en un seul passage.

        Cocher un par un via `setData()` rappelle `_emit_selection()` a
        chaque nodeid, qui recompte TOUTE la selection sur TOUT l'arbre
        (`checked_nodeids()`). Sur une suite de plusieurs milliers de tests,
        retenir ne serait-ce que quelques centaines de nodeids ainsi gele
        l'interface plusieurs secondes -- un cout quadratique invisible tant
        que la suite reste petite. Un seul recomptage a la fin suffit.

        `_set_checked()` a aussi un second cout, pire que celui-ci : chaque
        appel remonte jusqu'a la racine (visible) et emet `dataChanged` sur
        elle, ce qui force la vue a requalifier son tri-state -- une
        reconstruction COMPLETE et NON mise en cache de tout son sous-arbre
        (`_check_state`, recursif). Sur 5000 feuilles cochees dans une suite
        de 20000 tests, mesure : plus de 100 secondes, 110 millions d'appels
        a `_check_state`. Poser `checked` directement sur chaque feuille (un
        attribut, sans aucun signal) puis rafraichir une seule fois a la fin
        evite cette explosion : la vue ne requalifie chaque noeud visible
        qu'UNE fois, pas une fois par feuille cochee.
        """
        self.set_all_checked(False)
        retenus = set(nodeids)
        trouve = False
        for nodeid in retenus:
            ligne = self._by_nodeid.get(nodeid)
            if ligne is not None:
                ligne.checked = True
                trouve = True
        if trouve:
            self._refresh_checkbox_display()
        self._emit_selection()

    def _refresh_checkbox_display(self) -> None:
        """Invalide l'affichage des cases a cocher de tout l'arbre, une fois.

        Reutilise `_rafraichir_branche`, deja correct pour un noeud -- mais
        elle ne redessine que la DESCENDANCE de ce qu'on lui donne, jamais le
        noeud lui-meme. Chaque racine a donc besoin de son propre `dataChanged`
        en plus, sinon SA case ne se met jamais a jour.
        """
        for racine in self._roots:
            index = self.createIndex(racine.row, 0, racine)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            self._rafraichir_branche(racine)

    def checked_nodeids(self) -> list[str]:
        """Nodeids coches, dans l'ordre de l'arbre."""
        retenus = []
        for racine in self._roots:
            for feuille in racine.leaves():
                if feuille.checked:
                    retenus.append(feuille.node.nodeid)
        return retenus

    def counts(self) -> tuple[int, int]:
        total = sum(1 for r in self._roots for _ in r.leaves())
        coches = len(self.checked_nodeids())
        return coches, total

    def _emit_selection(self) -> None:
        coches, total = self.counts()
        self.selection_changed.emit(coches, total)

    # --------------------------------------------------------------- statuts

    def status_for(self, ligne: _Row, reader_index: int) -> Status:
        """Statut d'une ligne pour un lecteur.

        Une feuille porte le sien ; un regroupement montre le PIRE de ses
        enfants, sans quoi un echec au fond d'une arborescence repliee resterait
        invisible.

        Le resultat d'un regroupement est retenu : Qt appelle cette methode a
        chaque redessin, pour chaque ligne visible et chaque colonne, et le
        parcours complet du sous-arbre y etait refait a chaque fois.
        """
        if ligne.is_leaf:
            return ligne.statuses.get(reader_index, Status.PENDING)

        retenu = ligne.agg.get(reader_index)
        if retenu is None:
            retenu = worst(self.status_for(e, reader_index) for e in ligne.children)
            ligne.agg[reader_index] = retenu
        return retenu

    def apply_outcome(self, nodeid: str, status: Status, reader_index: int) -> bool:
        """Pose un resultat. Retourne False si le nodeid n'est pas dans l'arbre.

        Un resultat inconnu arrive quand la collecte n'est pas reproductible
        (identifiants de parametres tires au hasard) : l'appelant doit pouvoir
        le signaler plutot que de le perdre.
        """
        ligne = self._by_nodeid.get(nodeid)
        if ligne is None:
            return False

        # Le decompte suit le CHANGEMENT d'etat de la case, pas le nombre de
        # signaux recus. Compter les signaux part du principe que pytest
        # rapporte chaque test une fois et une seule ; il en rapporte deux pour
        # un test rejoue, ou pour une erreur de setup suivie d'un verdict. Le
        # compteur derivait alors du contenu reel de l'arbre.
        ancien = ligne.statuses.get(reader_index)
        if ancien is status:
            # Rien n'a change : le decompte serait de toute facon juste (on
            # retirerait puis remettrait le meme statut), mais tout le chemin
            # jusqu'a la racine serait repeint pour rien.
            return True
        if ancien is not None:
            self._tally[ancien] = max(0, self._tally.get(ancien, 0) - 1)
        self._tally[status] = self._tally.get(status, 0) + 1

        ligne.statuses[reader_index] = status
        colonne = 1 + reader_index if self._readers else 1

        index = self.createIndex(ligne.row, colonne, ligne)
        self.dataChanged.emit(index, index, [Qt.DecorationRole, Qt.ToolTipRole])

        # Les parents montrent le pire de leurs enfants : leur cellule change
        # aussi, sans qu'aucune donnee ne leur soit propre. Leur agregat est
        # mis a jour ici plutot qu'invalide : un resultat ne peut qu'aggraver
        # le pire connu, puisque tout repart de PENDING a chaque run
        # (`clear_statuses`). Recalculer aurait signifie reparcourir le
        # sous-arbre a chaque test qui se termine.
        parent = ligne.parent
        while parent is not None:
            connu = parent.agg.get(reader_index)
            parent.agg[reader_index] = (status if connu is None
                                        else worst((connu, status)))
            index_parent = self.createIndex(parent.row, colonne, parent)
            self.dataChanged.emit(index_parent, index_parent, [Qt.DecorationRole])
            parent = parent.parent
        return True

    def status_counts(self) -> dict:
        """Nombre de cases rendues par statut, tous lecteurs confondus.

        Autoritaire : c'est l'etat de l'arbre, pas une somme de signaux. Le
        nom ne peut pas etre `counts()`, deja pris par le decompte de la
        SELECTION -- deux notions differentes qui se seraient ecrasees.
        """
        return {s: n for s, n in self._tally.items() if n}

    def done(self) -> int:
        """Cases deja rendues, tous statuts et tous lecteurs confondus."""
        return sum(self._tally.values())

    def clear_statuses(self) -> None:
        """Efface les resultats sans reinitialiser le modele.

        Un beginResetModel replie tout l'arbre : au lancement d'un run,
        l'utilisateur perdait la branche qu'il venait d'ouvrir pour choisir ses
        tests. Seules les cellules de statut changent, on ne signale qu'elles.
        """
        self._tally.clear()
        for racine in self._roots:
            for ligne in [racine, *racine.descendants()]:
                ligne.statuses.clear()
                # Les agregats retenus valaient pour le run precedent : les
                # garder ferait afficher en rouge des dossiers remis a zero.
                ligne.agg.clear()

        colonnes = self.columnCount() - 1
        for racine in self._roots:
            for ligne in [racine, *racine.descendants()]:
                self.dataChanged.emit(
                    self.createIndex(ligne.row, 1, ligne),
                    self.createIndex(ligne.row, colonnes, ligne),
                    [Qt.DecorationRole, Qt.ToolTipRole],
                )

    def subtree_summary(self, index: QModelIndex) -> tuple[dict, list]:
        """Bilan de ce que contient ce noeud : compteurs et echecs.

        Rend `({index de lecteur: {statut: nombre}}, [(nodeid, lecteur), ...])`.
        Les echecs gardent l'ordre de l'arbre : la liste se relit comme la
        colonne de gauche, et non dans un ordre invente ici.
        """
        ligne = index.internalPointer() if index.isValid() else None
        if ligne is None:
            return {}, []

        indices = [r.index for r in self._readers] or [0]
        compteurs = {i: {} for i in indices}
        echecs: list[tuple[str, int]] = []

        for feuille in ligne.leaves():
            for i in indices:
                statut = feuille.statuses.get(i, Status.PENDING)
                compteurs[i][statut] = compteurs[i].get(statut, 0) + 1
                if statut.is_bad:
                    echecs.append((feuille.node.nodeid, i))
        return compteurs, echecs

    def first_leaf_nodeid(self, index: QModelIndex) -> str:
        """Nodeid d'un test quelconque sous ce noeud, ou "".

        Un regroupement n'a pas d'identifiant a lui. Celui d'une de ses
        feuilles suffit pourtant a retrouver le FICHIER -- il le porte avant
        son premier `::` -- et c'est ce qui permet d'ouvrir la source d'un
        module sur lequel on vient de cliquer.
        """
        ligne = index.internalPointer() if index.isValid() else None
        if ligne is None:
            return ""
        for feuille in ligne.leaves():
            return feuille.node.nodeid
        return ""

    def leaf_nodeids_under(self, index: QModelIndex) -> list[str]:
        """Tous les nodeids sous ce noeud, coches ou non.

        Pour "Run only this" depuis le menu contextuel d'un dossier ou d'un
        fichier : le geste porte sur ce qui est sous le clic, pas sur ce qui
        est coche ailleurs dans l'arbre.
        """
        ligne = index.internalPointer() if index.isValid() else None
        if ligne is None:
            return []
        return [feuille.node.nodeid for feuille in ligne.leaves()]

    def nodeids(self) -> list[str]:
        """Tous les nodeids de l'arbre, dans l'ordre ou il les montre."""
        retenus = []
        for racine in self._roots:
            for feuille in racine.leaves():
                retenus.append(feuille.node.nodeid)
        return retenus

    def failed_nodeids(self) -> list[str]:
        """Nodeids en echec sur au moins un lecteur."""
        retenus = []
        for racine in self._roots:
            for feuille in racine.leaves():
                if any(s.is_bad for s in feuille.statuses.values()):
                    retenus.append(feuille.node.nodeid)
        return retenus

    def failed_nodeids_for(self, reader_index: int) -> list[str]:
        """Nodeids en echec sur CE lecteur.

        L'historique garde une entree par lecteur : y mettre les echecs de
        tous ferait apparaitre, dans le bilan d'un lecteur, des tests qui n'ont
        echoue que sur l'autre.
        """
        retenus = []
        for racine in self._roots:
            for feuille in racine.leaves():
                statut = feuille.statuses.get(reader_index)
                if statut is not None and statut.is_bad:
                    retenus.append(feuille.node.nodeid)
        return retenus

    def divergent_nodeids(self) -> list[str]:
        """Nodeids dont les lecteurs ne rapportent pas le meme resultat.

        C'est la question centrale d'un run multi-lecteur : ou est-ce que les
        deux ne sont pas d'accord.
        """
        if len(self._readers) < 2:
            return []
        retenus = []
        for racine in self._roots:
            for feuille in racine.leaves():
                vus = {feuille.statuses.get(r.index, Status.PENDING) for r in self._readers}
                if len(vus) > 1:
                    retenus.append(feuille.node.nodeid)
        return retenus

    def statuses_for_nodeid(self, nodeid: str) -> dict[int, Status]:
        """Statut de ce test sur chaque lecteur declare.

        Toujours une entree par lecteur, PENDING compris : la fiche d'un test
        doit pouvoir dire « pas encore passe ici » plutot que d'omettre la
        colonne, ce qui se lirait comme un lecteur oublie.
        """
        ligne = self._by_nodeid.get(nodeid)
        if ligne is None:
            return {}
        indices = [r.index for r in self._readers] or [0]
        return {i: ligne.statuses.get(i, Status.PENDING) for i in indices}

    def index_for_nodeid(self, nodeid: str) -> QModelIndex:
        ligne = self._by_nodeid.get(nodeid)
        if ligne is None:
            return QModelIndex()
        return self.createIndex(ligne.row, 0, ligne)
