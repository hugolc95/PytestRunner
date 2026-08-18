"""L'onglet Source : lire un fichier de test, le corriger, l'enregistrer.

Ces tests ecrivent de vrais fichiers. C'est le sujet : on modifie les fichiers
de test de quelqu'un, et se tromper coute cher.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from runner.domain.source import (
    MAX_BYTES,
    function_line,
    path_of,
    read_source,
    write_source,
)

FICHIER = textwrap.dedent('''\
    import pytest


    @pytest.mark.smoke
    def test_atr():
        assert True


    async def test_secure_channel():
        assert True


    def test_select_aid(aid):
        assert aid
''')


@pytest.fixture
def source(tmp_path):
    chemin = tmp_path / "test_demo.py"
    # write_text traduit `\n` en `\r\n` sous Windows. Ici le fichier est
    # volontairement un echantillon LF : ecrire les octets rend le test reel.
    chemin.write_bytes(FICHIER.encode("utf-8"))
    return chemin


# =========================================================================
# Lecture
# =========================================================================


def test_a_file_comes_back_editable(source):
    fichier = read_source(source)
    assert fichier.loaded
    assert fichier.editable
    assert fichier.text == FICHIER
    assert not fichier.warning


def test_a_missing_file_explains_itself_instead_of_raising(tmp_path):
    fichier = read_source(tmp_path / "absent.py")
    assert not fichier.loaded
    assert not fichier.editable
    assert "Could not read" in fichier.warning


def test_a_file_that_is_not_utf8_is_read_only(tmp_path):
    """Le reecrire depuis ce qui est affiche remplacerait les octets illisibles
    par des points d'interrogation."""
    chemin = tmp_path / "test_bin.py"
    chemin.write_bytes(b"def test(): pass  # \xff\xfe binaire\n")

    fichier = read_source(chemin)
    assert fichier.loaded
    assert not fichier.editable
    assert "UTF-8" in fichier.warning


def test_a_truncated_file_is_read_only(tmp_path):
    """Enregistrer effacerait tout ce qui n'a pas ete lu."""
    chemin = tmp_path / "test_gros.py"
    chemin.write_bytes(b"# " + b"x" * (MAX_BYTES + 10))

    fichier = read_source(chemin)
    assert not fichier.editable
    assert "Truncated" in fichier.warning
    assert len(fichier.text) <= MAX_BYTES


def test_crlf_is_remembered(tmp_path):
    chemin = tmp_path / "test_win.py"
    chemin.write_bytes(b"def test():\r\n    pass\r\n")

    fichier = read_source(chemin)
    assert fichier.newline == "\r\n"
    # Affiche en LF : Qt ne doit pas montrer de caracteres parasites.
    assert "\r" not in fichier.text


def test_lf_stays_lf(source):
    assert read_source(source).newline == "\n"


# =========================================================================
# Ecriture
# =========================================================================


def test_saving_writes_what_was_shown(source):
    assert write_source(source, "def test_x(): pass\n") == ""
    assert source.read_text(encoding="utf-8") == "def test_x(): pass\n"


def test_saving_a_crlf_file_keeps_its_line_endings(tmp_path):
    """Sans cela, la premiere frappe convertirait tout le fichier et le diff
    ferait des milliers de lignes pour un caractere change."""
    chemin = tmp_path / "test_win.py"
    chemin.write_bytes(b"def test():\r\n    pass\r\n")

    write_source(chemin, "def test():\n    assert True\n", "\r\n")
    assert chemin.read_bytes() == b"def test():\r\n    assert True\r\n"


def test_a_failed_write_leaves_the_original_intact(tmp_path):
    """Une coupure en cours d'ecriture laisserait sinon un test a moitie ecrit,
    et la suite ne collecterait plus."""
    dossier = tmp_path / "sous"
    dossier.mkdir()
    chemin = dossier / "test_x.py"
    chemin.write_text("original\n", encoding="utf-8")

    # Un dossier a la place du fichier temporaire : `os.replace` echouera.
    (dossier / "test_x.py.pytestrunner.tmp").mkdir()

    erreur = write_source(chemin, "casse")
    assert erreur.startswith("Could not save")
    assert chemin.read_text(encoding="utf-8") == "original\n"


def test_no_temporary_file_is_left_behind(source):
    write_source(source, "def test_x(): pass\n")
    assert list(source.parent.glob("*.tmp")) == []


# =========================================================================
# Reperage
# =========================================================================


@pytest.mark.parametrize("nodeid, attendu", [
    ("test_demo.py::test_atr", 4),
    ("test_demo.py::test_secure_channel", 8),
    ("test_demo.py::test_select_aid[A001]", 12),
])
def test_the_cursor_lands_on_the_test_definition(nodeid, attendu):
    """Ouvrir un fichier de deux mille lignes tout en haut oblige a chercher a
    la main le test sur lequel on vient de cliquer."""
    assert function_line(FICHIER, nodeid) == attendu


def test_an_unknown_test_leaves_the_cursor_alone():
    assert function_line(FICHIER, "test_demo.py::test_jamais_vu") == -1


def test_a_blank_line_before_the_definition_is_not_matched():
    """`\\s` engloberait les sauts de ligne et le motif commencerait a matcher
    sur les lignes vides qui precedent, placant le curseur trop haut."""
    texte = "\n\n\ndef test_x():\n    pass\n"
    assert function_line(texte, "t.py::test_x") == 3


@pytest.mark.parametrize("nodeid, attendu", [
    ("suite/test_a.py::test_x", "suite/test_a.py"),
    ("suite/test_a.py::TestC::test_x[1]", "suite/test_a.py"),
    ("suite/dossier", None),
    ("", None),
])
def test_the_file_of_a_nodeid(nodeid, attendu, tmp_path):
    resultat = path_of(str(tmp_path), nodeid)
    assert resultat == (tmp_path / attendu if attendu else None)


# =========================================================================
# Le panneau
# =========================================================================


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def panneau(qapp):
    from runner.ui.source_panel import SourcePanel

    return SourcePanel()


def test_nothing_selected_shows_the_empty_state(panneau):
    assert panneau.stack.currentWidget() is panneau.empty


def test_opening_a_test_shows_its_file_and_jumps_to_it(panneau, source):
    panneau.show_file(source, "test_demo.py::test_secure_channel")

    assert panneau.stack.currentWidget() is not panneau.empty
    assert panneau.editor.toPlainText() == FICHIER
    assert panneau.editor.textCursor().blockNumber() == 8


def test_a_file_opens_read_only(panneau, source):
    """On ecrit dans de vrais fichiers de test : la bascule doit etre voulue."""
    panneau.show_file(source, "test_demo.py::test_atr")
    assert panneau.editor.isReadOnly()
    assert not panneau.edit_button.isChecked()
    assert panneau.edit_button.isEnabled()


def test_editing_then_saving_reaches_the_disk(panneau, source):
    panneau.show_file(source, "test_demo.py::test_atr")
    panneau.edit_button.setChecked(True)

    panneau.editor.setPlainText("def test_neuf(): pass\n")
    assert panneau.dirty

    assert panneau.save()
    assert source.read_text(encoding="utf-8") == "def test_neuf(): pass\n"
    assert not panneau.dirty


def test_a_read_only_file_cannot_be_switched_to_editing(panneau, tmp_path):
    chemin = tmp_path / "test_bin.py"
    chemin.write_bytes(b"# \xff\xfe\n")
    panneau.show_file(chemin, "test_bin.py::test_x")

    panneau.edit_button.setChecked(True)
    assert panneau.editor.isReadOnly()
    assert not panneau.edit_button.isEnabled()


def test_typing_while_read_only_never_writes(panneau, source):
    """Le chargement du fichier declenche lui aussi textChanged : il ne doit
    pas passer pour une modification de l'utilisateur."""
    panneau.show_file(source, "test_demo.py::test_atr")
    assert not panneau.dirty
    assert source.read_text(encoding="utf-8") == FICHIER


def test_switching_test_saves_what_was_pending(panneau, source, tmp_path):
    """Une frappe en attente ne doit pas disparaitre parce qu'on clique
    ailleurs."""
    autre = tmp_path / "test_autre.py"
    autre.write_text("def test_b(): pass\n", encoding="utf-8")

    panneau.show_file(source, "test_demo.py::test_atr")
    panneau.edit_button.setChecked(True)
    panneau.editor.setPlainText("def test_corrige(): pass\n")

    panneau.show_file(autre, "test_autre.py::test_b")

    assert source.read_text(encoding="utf-8") == "def test_corrige(): pass\n"


def test_editing_does_not_survive_a_change_of_file(panneau, source, tmp_path):
    """Reactiver explicitement rappelle qu'on ecrit dans un vrai fichier."""
    autre = tmp_path / "test_autre.py"
    autre.write_text("def test_b(): pass\n", encoding="utf-8")

    panneau.show_file(source, "test_demo.py::test_atr")
    panneau.edit_button.setChecked(True)
    panneau.show_file(autre, "test_autre.py::test_b")

    assert not panneau.edit_button.isChecked()
    assert panneau.editor.isReadOnly()


def test_leaving_edit_mode_saves(panneau, source):
    panneau.show_file(source, "test_demo.py::test_atr")
    panneau.edit_button.setChecked(True)
    panneau.editor.setPlainText("def test_z(): pass\n")

    panneau.edit_button.setChecked(False)
    assert source.read_text(encoding="utf-8") == "def test_z(): pass\n"


def test_a_write_error_is_reported_and_save_returns_false(panneau, tmp_path):
    dossier = tmp_path / "sous"
    dossier.mkdir()
    chemin = dossier / "test_x.py"
    chemin.write_text("original\n", encoding="utf-8")

    panneau.show_file(chemin, "test_x.py::test_x")
    panneau.edit_button.setChecked(True)
    panneau.editor.setPlainText("casse\n")

    (dossier / "test_x.py.pytestrunner.tmp").mkdir()
    assert not panneau.save()
    assert "Could not save" in panneau.status_label.text()
    assert chemin.read_text(encoding="utf-8") == "original\n"


def test_the_autosave_timer_fires_on_its_own(panneau, source, qapp):
    """C'est la promesse faite a l'utilisateur : il n'a pas de Ctrl+S a faire."""
    from PyQt5.QtCore import QEventLoop, QTimer

    panneau.show_file(source, "test_demo.py::test_atr")
    panneau.edit_button.setChecked(True)
    panneau.editor.setPlainText("def test_auto(): pass\n")

    boucle = QEventLoop()
    QTimer.singleShot(1200, boucle.quit)
    boucle.exec_()

    assert source.read_text(encoding="utf-8") == "def test_auto(): pass\n"


# =========================================================================
# La barre de commande
# =========================================================================


@pytest.fixture
def fenetre(qapp, tmp_path):
    """Une fenetre chargee sur un workspace reel, sans lancer de run."""
    from PyQt5.QtCore import QSettings

    from runner.domain.tree import build_tree
    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    (tmp_path / "test_demo.py").write_text(FICHIER, encoding="utf-8")

    w = MainWindow()
    w.workspace = __import__("runner.domain.workspace", fromlist=["Workspace"]) \
        .Workspace.load(str(tmp_path))
    w.model.set_tree(build_tree(["test_demo.py::test_atr",
                                 "test_demo.py::test_secure_channel"]))
    return w


def test_run_and_stop_do_not_share_a_colour(fenetre):
    """Vert / rouge est la convention de tous les lanceurs de tests : ce sont
    les deux gestes qu'on cherche sans lire."""
    assert fenetre.run_button.objectName() == "Run"
    assert fenetre.stop_button.objectName() == "Danger"


def test_rerun_failed_is_a_button_not_only_a_menu_entry(fenetre):
    """Apres un run rouge, relancer les seuls echecs est l'action suivante une
    fois sur deux."""
    assert fenetre.rerun_button.text() == "Re-run failed"
    assert fenetre.rerun_button.isVisibleTo(fenetre)


def test_rerun_stays_off_until_something_has_failed(fenetre):
    from runner.domain.models import Status

    fenetre._update_actions()
    assert not fenetre.rerun_button.isEnabled()

    fenetre.model.apply_outcome("test_demo.py::test_atr", Status.FAILED, 0)
    fenetre._update_actions()
    assert fenetre.rerun_button.isEnabled()
    assert fenetre.act_rerun.isEnabled()


def test_a_run_always_starts_from_the_file_on_screen(fenetre, tmp_path):
    """Le piege : corriger un test, lancer aussitot, et voir l'ancien code
    echouer a nouveau sans comprendre."""
    lances = []
    fenetre.service.start = lambda requete, env: lances.append(requete) or True

    chemin = tmp_path / "test_demo.py"
    fenetre.results.source.show_file(chemin, "test_demo.py::test_atr")
    fenetre.results.source.edit_button.setChecked(True)
    fenetre.results.source.editor.setPlainText("def test_atr(): assert False\n")

    fenetre._start(["test_demo.py::test_atr"])

    assert lances, "le run n'a pas ete lance"
    assert chemin.read_text(encoding="utf-8") == "def test_atr(): assert False\n"
    assert not fenetre.results.source.dirty


def test_a_run_is_refused_when_the_file_could_not_be_saved(fenetre, tmp_path, monkeypatch):
    """Lancer sur une version perimee vaut moins que ne pas lancer du tout."""
    from runner.ui import main_window as mw

    lances = []
    fenetre.service.start = lambda requete, env: lances.append(requete) or True
    monkeypatch.setattr(mw.ErrorDialog, "show_error",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(fenetre.results.source, "save", lambda: False)

    fenetre._start(["test_demo.py::test_atr"])
    assert lances == []
