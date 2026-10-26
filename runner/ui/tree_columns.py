"""Garde les colonnes de resultat visibles quand l'arbre retrecit."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer


class NameColumnFitter(QObject):
    """La colonne des noms cede la place, jamais les colonnes Status / Duration.

    Sa largeur reste celle que l'utilisateur a choisie (ou restauree) tant
    qu'elle tient. Quand le panneau devient trop etroit, elle se reduit juste
    assez pour que les colonnes de droite restent a l'ecran ; elle retrouve sa
    largeur choisie des que la place revient. Avant, ces colonnes partaient
    hors champ derriere une barre de defilement horizontale.
    """

    MINIMUM = 100

    def __init__(self, tree, parent=None):
        super().__init__(parent or tree)
        self._tree = tree
        self._preferred = tree.columnWidth(0)
        self._fitting = False
        header = tree.header()
        header.sectionResized.connect(self._on_section_resized)
        tree.viewport().installEventFilter(self)
        # Apres un changement de lecteurs, la largeur des colonnes de droite
        # change sans que le panneau bouge.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.fit)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            # Jamais pendant le redimensionnement lui-meme : la vue peut etre
            # en train de remettre son modele a zero (expandAll, set_tree).
            self._timer.start()
        return False

    def _on_section_resized(self, index: int, _old: int, new: int) -> None:
        if self._fitting:
            return
        if index == 0:
            self._preferred = new
        else:
            self._timer.start()

    def fit(self) -> None:
        header = self._tree.header()
        others = sum(header.sectionSize(i) for i in range(1, header.count())
                     if not header.isSectionHidden(i))
        available = self._tree.viewport().width() - others
        width = max(self.MINIMUM, min(self._preferred, available))
        if width == header.sectionSize(0):
            return
        self._fitting = True
        try:
            header.resizeSection(0, width)
        finally:
            self._fitting = False


class TreeColumnLayout(QObject):
    """Largeurs des colonnes de l'arbre, retenues colonne par colonne, et
    affichage de la colonne Duration.

    Les largeurs etaient recalculees a chaque collecte qui changeait de
    lecteurs, et a chaque demarrage : un reglage fait a la souris ne tenait
    pas. Elles sont maintenant retenues par IDENTITE de colonne -- Test, nom du
    lecteur, Duration -- et non par position, qui change avec le nombre de
    lecteurs. Seuls les gestes de l'utilisateur sont retenus : les ajustements
    automatiques (cession de place de la colonne Test, remise a zero du
    modele) ne doivent pas ecraser son choix.
    """

    SETTINGS_KEY = "tree/column_widths"
    NAME_DEFAULT = 420
    # Une duree de plus d'une heure reste lisible en elargissant la colonne.
    DURATION_SAMPLE = "10 min 59.9s"

    def __init__(self, tree, settings, fitter: NameColumnFitter, default_width, parent=None):
        super().__init__(parent or tree)
        self._tree = tree
        self._default_width = default_width
        self._settings = settings
        self._fitter = fitter
        self._programmatic = 0
        self._duration_visible = True
        self._widths = self._load()
        header = tree.header()
        header.sectionResized.connect(self._on_section_resized)
        # Le nombre de colonnes suit celui des lecteurs : Duration change
        # d'index, et l'etat masque d'une section resterait sur l'ancien.
        header.sectionCountChanged.connect(lambda *_: self._apply_visibility())
        tree.model().modelReset.connect(self._apply_visibility)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save)
        if "name" in self._widths:
            self._set_name_width(self._widths["name"])

    # ------------------------------------------------------------ memoire

    def _load(self) -> dict:
        import json

        try:
            data = json.loads(self._settings.value(self.SETTINGS_KEY, "{}", type=str) or "{}")
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items()
                if isinstance(v, (int, float)) and 24 <= v <= 4000}

    def _save(self) -> None:
        import json

        self._settings.setValue(self.SETTINGS_KEY, json.dumps(self._widths, sort_keys=True))

    def key(self, section: int) -> str | None:
        model = self._tree.model()
        if model is None or section < 0:
            return None
        if section == 0:
            return "name"
        if section == getattr(model, "duration_column", -1):
            return "duration"
        readers = getattr(model, "readers", ())
        if not readers:
            return "status" if section == 1 else None
        if 1 <= section <= len(readers):
            return f"reader:{readers[section - 1].name}"
        return None

    def remembered(self, section: int) -> int | None:
        key = self.key(section)
        return self._widths.get(key) if key else None

    def _user_gesture(self) -> bool:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        return bool(QApplication.mouseButtons() & Qt.LeftButton)

    def _on_section_resized(self, section: int, _old: int, new: int) -> None:
        if self._programmatic or self._fitter._fitting or new <= 0:
            return
        if not self._user_gesture():
            return
        self.remember(section, new)

    def remember(self, section: int, width: int) -> None:
        key = self.key(section)
        if key is None:
            return
        self._widths[key] = int(width)
        self._save_timer.start()

    # ------------------------------------------------------------ largeurs

    def _resize(self, section: int, width: int) -> None:
        self._programmatic += 1
        try:
            self._tree.header().resizeSection(section, width)
        finally:
            self._programmatic -= 1

    def _set_name_width(self, width: int) -> None:
        self._fitter._preferred = width
        self._resize(0, width)
        self._fitter._timer.start()

    def duration_default(self) -> int:
        header = self._tree.header()
        title = header.fontMetrics().horizontalAdvance("Duration") + 28
        value = self._tree.fontMetrics().horizontalAdvance(self.DURATION_SAMPLE) + 24
        return max(72, title, value)

    def size_columns(self) -> None:
        """Chaque colonne reprend sa largeur retenue, sinon `default_width(section)`."""
        from PySide6.QtWidgets import QHeaderView

        header = self._tree.header()
        model = self._tree.model()
        for section in range(1, model.columnCount()):
            header.setSectionResizeMode(section, QHeaderView.Interactive)
            width = self.remembered(section)
            if width is None:
                width = (self.duration_default() if self.key(section) == "duration"
                         else self._default_width(section))
            self._resize(section, width)
        self._apply_visibility()
        self._fitter._timer.start()

    def reapply(self) -> None:
        """Apres un `restoreState` de l'en-tete (demarrage, onglet de run).

        Les largeurs restaurees sont celles de ce run : elles deviennent les
        largeurs retenues de leurs colonnes. L'etat masque, lui, peut dater
        d'un autre nombre de colonnes -- l'affichage de Duration est reimpose.
        """
        header = self._tree.header()
        for section in range(header.count()):
            width = header.sectionSize(section)
            key = self.key(section)
            if key is not None and width >= 24 and not header.isSectionHidden(section):
                self._widths[key] = width
        self._save_timer.start()
        self._fitter._preferred = header.sectionSize(0)
        self._apply_visibility()
        self._fitter._timer.start()

    def reset(self) -> None:
        """Oublie les reglages : largeurs calculees, colonne Test comprise."""
        self._widths.clear()
        self._save_timer.stop()
        self._save()
        self._set_name_width(self.NAME_DEFAULT)
        self.size_columns()

    # ------------------------------------------------------------ Duration

    @property
    def duration_visible(self) -> bool:
        return self._duration_visible

    def set_duration_visible(self, visible: bool) -> None:
        self._duration_visible = bool(visible)
        self._apply_visibility()
        self._fitter._timer.start()

    def _apply_visibility(self) -> None:
        model = self._tree.model()
        header = self._tree.header()
        if model is None:
            return
        duration = getattr(model, "duration_column", -1)
        for section in range(1, header.count()):
            hidden = section == duration and not self._duration_visible
            if header.isSectionHidden(section) != hidden:
                header.setSectionHidden(section, hidden)
