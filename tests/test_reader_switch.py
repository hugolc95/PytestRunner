"""Choisir le lecteur sans rien demander au code de test.

Les tests d'un workspace lisent UN lecteur, par un `getConfigReader()` qui va
chercher la cle `Reader`. Plusieurs lecteurs n'y sont pas prevus. L'interface
s'en charge donc a leur place : elle ecrit le lecteur voulu dans cette cle avant
chaque lancement et remet la valeur d'origine ensuite, les lecteurs etant joues
l'un apres l'autre.

L'ecriture se fait a la ligne, pas en reserialisant le YAML : le fichier de
configuration d'un vrai projet a des commentaires, un ordre de cles et une mise
en forme qu'un yaml.safe_dump detruirait.
"""

import textwrap
from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

from core.reader_switch import (
    ActiveReader,
    read_active_reader,
    restore_interrupted_reader,
    set_active_reader,
)
from core.workspace_config import reader_mode_for

CONFIG = textwrap.dedent('''\
    # Configuration du workspace
    LOG_PATH: C:\\__LOGS__\\CryptoWrapper

    Reader: Infineon CryptoWrapperTU Reader 0   # lecteur actif
    Mode: PERSO

    Debug:
      Reader: ignore, c'est un reglage de mode
      RSAkey: 3072
    ''')


@pytest.fixture
def config(tmp_path):
    chemin = tmp_path / "configWorkspace.yml"
    chemin.write_text(CONFIG, encoding="utf-8")
    return chemin


# ------------------------------------------------------------- ecriture ciblee

def test_the_active_reader_is_read(config):
    assert read_active_reader(config) == "Infineon CryptoWrapperTU Reader 0"


def test_writing_a_reader_returns_the_previous_one(config):
    ancien = set_active_reader(config, "Infineon CryptoWrapperTU Reader 1")
    assert ancien == "Infineon CryptoWrapperTU Reader 0"
    assert read_active_reader(config) == "Infineon CryptoWrapperTU Reader 1"


def test_nothing_else_in_the_file_moves(config):
    """Le point critique : un vrai fichier a des commentaires, un ordre de cles
    et une mise en forme qu'un yaml.safe_dump detruirait."""
    set_active_reader(config, "Reader 1")
    lignes = config.read_text(encoding="utf-8").splitlines()

    assert lignes[0] == "# Configuration du workspace"
    assert lignes[1] == "LOG_PATH: C:\\__LOGS__\\CryptoWrapper"
    assert lignes[4] == "Mode: PERSO"
    assert "  RSAkey: 3072" in lignes


def test_the_end_of_line_comment_survives(config):
    set_active_reader(config, "Reader 1")
    ligne = [l for l in config.read_text(encoding="utf-8").splitlines()
             if l.startswith("Reader:")][0]
    assert ligne == "Reader: Reader 1 # lecteur actif"


def test_a_reader_inside_a_section_is_left_alone(config):
    """La cle la moins indentee est celle que lisent les tests ; celle d'une
    section n'est qu'un reglage de mode."""
    set_active_reader(config, "Reader 1")
    assert "  Reader: ignore, c'est un reglage de mode" in \
        config.read_text(encoding="utf-8")


def test_a_value_needing_quotes_gets_them(config):
    set_active_reader(config, "Lecteur: bizarre")
    assert read_active_reader(config) == "Lecteur: bizarre"


def test_a_config_without_a_reader_key_is_untouched(tmp_path):
    """Rien a changer, et surtout rien a inventer."""
    chemin = tmp_path / "config.yml"
    chemin.write_text("LOG_PATH: traces\n", encoding="utf-8")

    assert set_active_reader(chemin, "Reader 1") is None
    assert chemin.read_text(encoding="utf-8") == "LOG_PATH: traces\n"


def test_crlf_line_endings_are_preserved(tmp_path):
    chemin = tmp_path / "config.yml"
    chemin.write_bytes(b"Reader: R0\r\nMode: PERSO\r\n")

    set_active_reader(chemin, "R1")

    assert chemin.read_bytes() == b"Reader: R1\r\nMode: PERSO\r\n"


# --------------------------------------------------- le temps d'un run seulement

def test_the_original_reader_comes_back(config):
    with ActiveReader(config, "Reader 1"):
        assert read_active_reader(config) == "Reader 1"

    assert read_active_reader(config) == "Infineon CryptoWrapperTU Reader 0"


def test_the_original_comes_back_even_on_error(config):
    with pytest.raises(RuntimeError):
        with ActiveReader(config, "Reader 1"):
            raise RuntimeError("le run a echoue")

    assert read_active_reader(config) == "Infineon CryptoWrapperTU Reader 0"


def test_an_interrupted_run_can_be_repaired(config):
    """Une coupure en plein run laisserait la configuration sur le dernier
    lecteur essaye, sans que personne ne s'en apercoive."""
    contexte = ActiveReader(config, "Reader 1")
    contexte.__enter__()  # pas de __exit__ : on simule la coupure

    assert read_active_reader(config) == "Reader 1"
    assert restore_interrupted_reader(config) == "Infineon CryptoWrapperTU Reader 0"
    assert read_active_reader(config) == "Infineon CryptoWrapperTU Reader 0"


def test_repairing_a_clean_config_does_nothing(config):
    assert restore_interrupted_reader(config) is None
    assert read_active_reader(config) == "Infineon CryptoWrapperTU Reader 0"


def test_no_marker_is_left_behind(config):
    with ActiveReader(config, "Reader 1"):
        pass
    assert list(config.parent.glob("*backup*")) == []


# --------------------------------------------------------------- enchainement

def test_parallel_is_the_default(tmp_path):
    """Rien a declarer : le plugin (core/reader_plugin.py) rend le fichier de
    configuration virtuellement different pour chaque process sans ecrire nulle
    part, donc sans risque pour un workspace qui n'a rien configure."""
    assert reader_mode_for(str(tmp_path)) == "parallel"


def test_sequential_can_be_asked_for(tmp_path):
    (tmp_path / "config.yml").write_text("reader_mode: sequential\n", encoding="utf-8")
    assert reader_mode_for(str(tmp_path)) == "sequential"


def test_parallel_can_be_asked_for_explicitly(tmp_path):
    (tmp_path / "config.yml").write_text("reader_mode: parallel\n", encoding="utf-8")
    assert reader_mode_for(str(tmp_path)) == "parallel"


READERS = ["Lecteur A", "Lecteur B"]


@pytest.fixture
def window(qtbot, tmp_path):
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    # reader_mode: sequential explicite : ces tests portent sur le mecanisme
    # sequentiel lui-meme (ecriture dans la configuration, un run a la fois,
    # restauration), plus choisi par defaut depuis que le parallele est sans
    # risque.
    (tmp_path / "config.yml").write_text(
        "reader_mode: sequential\n"
        "Reader: Lecteur A\nReaders:\n  - Lecteur A\n  - Lecteur B\n", encoding="utf-8")
    # Le test note le lecteur que la configuration lui donnait, comme le ferait
    # un getConfigReader() reel.
    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import pathlib
        import yaml

        def test_f():
            config = pathlib.Path(__file__).with_name("config.yml")
            lecteur = yaml.safe_load(config.read_text(encoding="utf-8"))["Reader"]
            pathlib.Path(__file__).with_name("vu_" + lecteur.replace(" ", "_")).touch()
    '''), encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()
    return fenetre


def test_the_tests_see_each_reader_in_turn(window, qtbot):
    """Le coeur du sujet : les tests lisent `Reader`, sans rien connaitre du
    multi-lecteur, et voient pourtant chacun des lecteurs."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: window._runs_left == 0, timeout=120000)

        temoins = sorted(p.name for p in Path(window.workspace).glob("vu_*"))
        assert temoins == ["vu_Lecteur_A", "vu_Lecteur_B"]
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


def test_the_sequential_choice_is_explained_in_the_console(window, qtbot):
    """Le sequentiel est un choix explicite (reader_mode: sequential) depuis
    que le parallele est le defaut : la console doit dire ce qui est arrive."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        window._flush_console_output()
        assert "l'un apres l'autre" in window.console.toPlainText()
        assert "reader_mode: sequential" in window.console.toPlainText()
    finally:
        qtbot.waitUntil(lambda: window._runs_left == 0, timeout=120000)
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


def test_no_sequential_note_in_parallel_mode(parallele, qtbot):
    """En parallele (le defaut), aucun avertissement de secours n'a lieu d'etre."""
    parallele._launch_worker(["test_x.py::TestSuite::test_f"], "run\n")
    try:
        parallele._flush_console_output()
        sortie = "".join(parallele.details.console_for(i).toPlainText()
                         for i in range(3))
        assert "l'un apres l'autre" not in sortie
    finally:
        qtbot.waitUntil(lambda: parallele._runs_left == 0, timeout=120000)
        for worker in parallele.workers:
            worker.stop()
            worker.wait(10000)


def test_the_configuration_is_left_as_it_was(window, qtbot):
    """Le signal de fin part de l'interieur du bloc qui restaure : il faut donc
    attendre la sortie du thread avant de relire le fichier."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: window._runs_left == 0, timeout=120000)
        for worker in window.workers:
            worker.wait(5000)

        assert read_active_reader(Path(window.workspace) / "config.yml") == "Lecteur A"
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


def test_only_one_process_runs_at_a_time(window, qtbot):
    """Deux processus simultanes se disputeraient le fichier de configuration."""
    window._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        actifs = [w for w in window.workers if w.isRunning()]
        assert len(actifs) <= 1
        qtbot.waitUntil(lambda: window._runs_left == 0, timeout=120000)
    finally:
        for worker in window.workers:
            worker.stop()
            worker.wait(5000)


def test_stopping_does_not_start_the_next_reader(window, qtbot):
    """Arreter doit arreter, pas enchainer sur le lecteur suivant.

    On regarde le lecteur suivant plutot que l'etat des threads : isRunning()
    reste brievement vrai apres le signal de fin, ce qui rendrait le test
    dependant du moment ou on l'interroge.
    """
    window._launch_worker(["test_x.py::test_f"], "run\n")
    window.stop_tests()
    qtbot.waitUntil(lambda: window._runs_left == 0, timeout=120000)
    for worker in window.workers:
        worker.wait(5000)

    assert not (Path(window.workspace) / "vu_Lecteur_B").exists()


def test_parallel_mode_does_not_touch_the_configuration(qtbot, tmp_path):
    """En parallele le lecteur passe par l'environnement : y toucher serait une
    course entre les deux processus."""
    from gui_qt.main_window import MainWindow

    (tmp_path / "config.yml").write_text(
        "reader_mode: parallel\nReader: A\nReaders:\n  - A\n  - B\n", encoding="utf-8")
    (tmp_path / "test_x.py").write_text("def test_f():\n    pass\n", encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.refresh_readers()
    fenetre._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        assert all(not w.write_reader_to_config for w in fenetre.workers)
        assert len([w for w in fenetre.workers if w.isRunning()]) >= 1
    finally:
        for worker in fenetre.workers:
            worker.stop()
            worker.wait(5000)


# --------------------------------------------- champ Reader de la configuration

def test_the_reader_field_is_a_dropdown(qtbot):
    from gui_qt.config.config_form import ConfigForm

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "Lecteur A", "Readers": ["Lecteur A", "Lecteur B"]})

    champ = form.field("Reader")
    assert champ.widget.isEditable(), "un lecteur debranche doit rester saisissable"
    propositions = [champ.widget.itemText(i) for i in range(champ.widget.count())]
    assert propositions == ["Lecteur A", "Lecteur B"]


def test_adding_opens_an_empty_field_below(qtbot):
    """"+" ouvre une place pour un AUTRE lecteur, il ne duplique pas celui qui
    est deja choisi."""
    from gui_qt.config.config_form import ConfigForm

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "Lecteur A", "Mode": "PERSO"})

    form.field("Reader").add_button.click()

    champ = form.field("Readers")
    assert champ is not None, "un champ de lecteur supplementaire est apparu"
    assert len(champ.rows) == 1
    assert champ.rows[0].currentText() == ""
    assert champ.rows[0].isEditable(), "un champ comme le lecteur principal"


def test_the_added_field_is_a_dropdown_too(qtbot, monkeypatch):
    from gui_qt.config import config_form

    monkeypatch.setattr(config_form, "available_readers",
                        lambda connus=None: ["Detecte 0", "Detecte 1"])
    form = config_form.ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "Detecte 0"})

    form.field("Reader").add_button.click()
    combo = form.field("Readers").rows[0]

    assert [combo.itemText(i) for i in range(combo.count())] == ["Detecte 0", "Detecte 1"]


def test_the_reader_key_is_never_touched(qtbot):
    """C'est `Reader` que lisent les tests : l'ecraser casserait le workspace."""
    from gui_qt.config.config_form import ConfigForm

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "Lecteur A", "Mode": "PERSO"})

    form.field("Reader").add_button.click()
    form.field("Readers").rows[0].setCurrentText("Lecteur B")

    valeurs = form.values()
    assert valeurs["Reader"] == "Lecteur A"
    assert valeurs["Readers"] == ["Lecteur B"]
    assert valeurs["Mode"] == "PERSO", "le reste de la configuration est intact"


def test_each_added_reader_gets_its_own_field(qtbot):
    from gui_qt.config.config_form import ConfigForm

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "A", "Readers": ["B"]})

    form.field("Reader").add_button.click()
    form.field("Readers").rows[-1].setCurrentText("C")

    assert form.values()["Readers"] == ["B", "C"]


def test_an_empty_field_is_not_written(qtbot):
    """Un lecteur sans nom ne designe rien et ferait un run de plus sans objet."""
    from gui_qt.config.config_form import ConfigForm

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "A", "Readers": ["B"]})

    form.field("Reader").add_button.click()

    assert form.values()["Readers"] == ["B"]


def test_a_reader_can_be_removed(qtbot):
    from gui_qt.config.config_form import ConfigForm

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "A", "Readers": ["B", "C"]})

    champ = form.field("Readers")
    champ._retirer(champ.rows[0].parentWidget(), champ.rows[0])

    assert form.values()["Readers"] == ["C"]


def test_the_extra_readers_come_after_the_main_one(tmp_path):
    """`Readers` liste ceux qu'on veut EN PLUS de celui de la configuration."""
    from core.workspace_config import readers_for

    (tmp_path / "config.yml").write_text(
        "Reader: Lecteur A\nReaders:\n  - Lecteur B\n", encoding="utf-8")

    assert readers_for(str(tmp_path)) == ["Lecteur A", "Lecteur B"]


def test_the_detection_hook_feeds_the_dropdown(qtbot, monkeypatch):
    """La fonction que l'utilisateur branchera dans reader_sources.py."""
    from gui_qt.config import config_form

    monkeypatch.setattr(config_form, "available_readers",
                        lambda connus=None: ["Detecte 0", "Detecte 1"])

    form = config_form.ConfigForm()
    qtbot.addWidget(form)
    form.load({"Reader": "Detecte 0"})

    champ = form.field("Reader")
    assert [champ.widget.itemText(i) for i in range(champ.widget.count())] == \
        ["Detecte 0", "Detecte 1"]


def test_a_failing_detection_does_not_break_the_window(monkeypatch):
    """Service PC/SC arrete, DLL absente, lecteur retire : rien de tout cela ne
    doit empecher d'ouvrir la configuration."""
    from gui_qt.config import reader_sources

    def explose():
        raise OSError("service de cartes a puce arrete")

    monkeypatch.setattr(reader_sources, "list_connected_readers", explose)
    assert reader_sources.available_readers(["Deja connu"]) == ["Deja connu"]


def test_a_disconnected_reader_stays_selectable():
    """Sans cela, rouvrir la configuration ferait disparaitre le reglage."""
    from gui_qt.config.reader_sources import available_readers

    assert available_readers(["Lecteur debranche"]) == ["Lecteur debranche"]


def test_loading_a_workspace_repairs_an_interrupted_run(qtbot, tmp_path):
    """Le lecteur affiche aurait sinon change sans que personne ne l'ait demande."""
    from gui_qt.main_window import MainWindow

    config = tmp_path / "config.yml"
    config.write_text("Reader: Lecteur A\n", encoding="utf-8")
    ActiveReader(config, "Lecteur B").__enter__()  # coupure simulee
    assert read_active_reader(config) == "Lecteur B"

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre._on_workspace_loaded([], 0, str(tmp_path))
    fenetre._flush_console_output()

    assert read_active_reader(config) == "Lecteur A"
    assert "Lecteur remis a 'Lecteur A'" in fenetre.console.toPlainText()


# ------------------------------- parallele, sans toucher au code de test

@pytest.fixture
def parallele(qtbot, tmp_path):
    """Un workspace calque sur le votre : un config_getters.getConfigReader()
    qui lit la cle Reader, et une classe de test qui l'appelle dans son setup.

    Rien a declarer pour obtenir le parallele : c'est desormais le defaut, sans
    risque, des que plusieurs lecteurs sont a tester.
    """
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "config.yml").write_text(
        "Reader: Lecteur A\n"
        "Readers:\n  - Lecteur B\n  - Lecteur C\n",
        encoding="utf-8")

    (tmp_path / "config_getters.py").write_text(textwrap.dedent('''
        import pathlib
        import yaml

        def getConfigReader():
            config = pathlib.Path(__file__).with_name("config.yml")
            return yaml.safe_load(config.read_text(encoding="utf-8"))["Reader"]
    '''), encoding="utf-8")

    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import pathlib

        from config_getters import getConfigReader

        class TestSuite:
            def setup_method(self):
                self.reader = getConfigReader()

            def test_f(self):
                pathlib.Path(__file__).with_name(
                    "vu_" + self.reader.replace(" ", "_")).touch()
    '''), encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()
    return fenetre


def test_three_readers_run_at_once_each_with_its_own(parallele, qtbot):
    """Le but : trois pytest en meme temps, chacun voyant son lecteur, sans
    qu'une seule ligne du code de test ait change, et sans rien avoir eu a
    configurer -- le parallele est le defaut."""
    parallele._launch_worker(["test_x.py::TestSuite::test_f"], "run\n")
    try:
        assert len(parallele.workers) == 3
        assert len([w for w in parallele.workers if w.isRunning()]) >= 2, \
            "les processus doivent tourner ensemble, pas l'un apres l'autre"

        qtbot.waitUntil(lambda: parallele._runs_left == 0, timeout=120000)

        temoins = sorted(p.name for p in Path(parallele.workspace).glob("vu_*"))
        assert temoins == ["vu_Lecteur_A", "vu_Lecteur_B", "vu_Lecteur_C"]
    finally:
        for worker in parallele.workers:
            worker.stop()
            worker.wait(10000)


def test_the_configuration_is_never_written_in_parallel(parallele, qtbot):
    """Trois processus s'y disputeraient : le lecteur passe par le plugin."""
    parallele._launch_worker(["test_x.py::TestSuite::test_f"], "run\n")
    try:
        assert all(not w.write_reader_to_config for w in parallele.workers)
        qtbot.waitUntil(lambda: parallele._runs_left == 0, timeout=120000)
        assert read_active_reader(Path(parallele.workspace) / "config.yml") == "Lecteur A"
    finally:
        for worker in parallele.workers:
            worker.stop()
            worker.wait(10000)


def test_a_reader_key_the_plugin_cannot_locate_stops_the_run_loudly(qtbot, tmp_path):
    """`reader_config_path()` retrouve le fichier via un vrai parseur YAML, qui
    voit la cle Reader meme en notation JSON/flow (`{Reader: A, ...}`). Le
    plugin, lui, doit REECRIRE cette cle sans reserialiser tout le fichier
    (commentaires, ordre, mise en forme a preserver) : il travaille donc ligne
    a ligne, et une telle ligne n'a pas de `Reader:` isole a repointer.

    Continuer serait pire que s'arreter : tous les lecteurs liraient la meme
    valeur, sans que rien ne le signale.
    """
    from gui_qt.main_window import MainWindow

    (tmp_path / "config.yml").write_text(
        "{Reader: A, Readers: [A, B]}\n", encoding="utf-8")
    (tmp_path / "test_x.py").write_text(
        "def test_f():\n    pass\n", encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()

    fenetre._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: fenetre._runs_left == 0, timeout=120000)
        fenetre._flush_console_output()

        sortie = "".join(fenetre.details.console_for(i).toPlainText() for i in range(2))
        assert "n'a pas pu imposer le lecteur" in sortie
        assert "reader_mode: sequential" in sortie, "la sortie de secours est indiquee"
    finally:
        for worker in fenetre.workers:
            worker.stop()
            worker.wait(10000)


def test_the_reader_variable_is_set_alongside_the_plugin_in_parallel(qtbot, tmp_path):
    """La variable d'environnement reste disponible en plus du plugin, pour un
    workspace dont le code de test prefere la lire directement."""
    from gui_qt.main_window import MainWindow

    (tmp_path / "config.yml").write_text(
        "Reader: A\nReaders:\n  - B\n", encoding="utf-8")
    (tmp_path / "test_x.py").write_text(
        "def test_f():\n    pass\n", encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.refresh_readers()
    fenetre._launch_worker(["test_x.py::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: fenetre._runs_left == 0, timeout=120000)
        for worker in fenetre.workers:
            worker.wait(10000)

        assert all(w._plugin_args for w in fenetre.workers), \
            "le plugin doit etre injecte pour chaque lecteur en parallele"
        assert fenetre.workers[1]._env()["PYTESTRUNNER_READER"] == "B"
    finally:
        for worker in fenetre.workers:
            worker.stop()
            worker.wait(10000)


def test_the_generated_plugin_is_cleaned_up(parallele, qtbot):
    import tempfile

    avant = set(Path(tempfile.gettempdir()).glob("pytestrunner_plugin_*"))
    parallele._launch_worker(["test_x.py::TestSuite::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: parallele._runs_left == 0, timeout=120000)
        for worker in parallele.workers:
            worker.wait(10000)

        apres = set(Path(tempfile.gettempdir()).glob("pytestrunner_plugin_*"))
        assert apres == avant
    finally:
        for worker in parallele.workers:
            worker.stop()
            worker.wait(10000)


# --------------------------- le cas exact signale : getConfigReader dans conftest.py

@pytest.fixture
def parallele_conftest(qtbot, tmp_path):
    """Reproduction fidele du workspace signale : getConfigReader n'est pas
    dans un module a part, mais directement dans conftest.py. Sans importance
    pour le plugin, qui ne touche jamais a cette fonction ni a l'endroit ou
    elle vit -- seul le fichier qu'elle lit est rendu virtuellement different."""
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "config.yml").write_text(
        "Reader: Lecteur A\n"
        "Readers:\n  - Lecteur B\n  - Lecteur C\n",
        encoding="utf-8")

    (tmp_path / "conftest.py").write_text(textwrap.dedent('''
        import pathlib
        import yaml

        def getConfigReader():
            config = pathlib.Path(__file__).with_name("config.yml")
            return yaml.safe_load(config.read_text(encoding="utf-8"))["Reader"]
    '''), encoding="utf-8")

    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import pathlib

        from conftest import getConfigReader

        class TestSuite:
            def setup_method(self):
                self.reader = getConfigReader()

            def test_f(self):
                pathlib.Path(__file__).with_name(
                    "vu_" + self.reader.replace(" ", "_")).touch()
    '''), encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()
    return fenetre


def test_a_getter_living_directly_in_conftest_works(parallele_conftest, qtbot):
    """Le cas signale mot pour mot : "ma fonction de getConfigReader est dans
    le conftest". Trois pytest en meme temps, chacun voyant son lecteur, sans
    modifier ni conftest.py ni test_x.py."""
    parallele_conftest._launch_worker(["test_x.py::TestSuite::test_f"], "run\n")
    try:
        assert len(parallele_conftest.workers) == 3
        assert len([w for w in parallele_conftest.workers if w.isRunning()]) >= 2, \
            "les processus doivent tourner ensemble, pas l'un apres l'autre"

        qtbot.waitUntil(lambda: parallele_conftest._runs_left == 0, timeout=120000)

        temoins = sorted(p.name for p in Path(parallele_conftest.workspace).glob("vu_*"))
        assert temoins == ["vu_Lecteur_A", "vu_Lecteur_B", "vu_Lecteur_C"]
    finally:
        for worker in parallele_conftest.workers:
            worker.stop()
            worker.wait(10000)


# ----------------------------------------- le bug signale : un getter qui enrichit


@pytest.fixture
def parallele_getter_enrichi(qtbot, tmp_path):
    """Reproduction du bug signale mot pour mot : "mon getter rajoute un petit
    champs dans la string qui n'est pas pris en compte au lancement des tests".

    Le getter ne se contente pas de relire `Reader` : il lui ajoute un suffixe,
    comme le ferait un formatage ou un champ construit reel. Comme il n'est
    JAMAIS remplace -- seul le fichier qu'il lit est rendu virtuellement
    different -- cet ajout doit survivre intact au lancement en parallele.
    """
    from gui_qt.main_window import MainWindow

    QSettings("MyCompany", "PyTestRunner").setValue("theme", "light")
    (tmp_path / "config.yml").write_text(
        "Reader: Lecteur A\n"
        "Readers:\n  - Lecteur B\n  - Lecteur C\n",
        encoding="utf-8")

    (tmp_path / "conftest.py").write_text(textwrap.dedent('''
        import pathlib
        import yaml

        def getConfigReader():
            config = pathlib.Path(__file__).with_name("config.yml")
            lecteur = yaml.safe_load(config.read_text(encoding="utf-8"))["Reader"]
            # Le getter reel de l'utilisateur ne se contente pas de relire la
            # cle : il lui ajoute un champ.
            return lecteur + " [verifie]"
    '''), encoding="utf-8")

    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import pathlib

        from conftest import getConfigReader

        class TestSuite:
            def setup_method(self):
                self.reader = getConfigReader()

            def test_f(self):
                pathlib.Path(__file__).with_name(
                    "vu_" + self.reader.replace(" ", "_")).touch()
    '''), encoding="utf-8")

    fenetre = MainWindow()
    qtbot.addWidget(fenetre)
    fenetre.workspace = str(tmp_path)
    fenetre.details.set_workspace(str(tmp_path))
    fenetre.refresh_readers()
    return fenetre


def test_a_getter_that_enriches_the_reader_keeps_its_enrichment_in_parallel(
        parallele_getter_enrichi, qtbot):
    """Avec l'ancien remplacement de fonction, ce '[verifie]' disparaissait :
    toute la fonction etait remplacee par une simple valeur figee. Ici
    getConfigReader() tourne sans la moindre modification, donc son ajout se
    retrouve, intact, dans les trois temoins."""
    parallele_getter_enrichi._launch_worker(["test_x.py::TestSuite::test_f"], "run\n")
    try:
        qtbot.waitUntil(lambda: parallele_getter_enrichi._runs_left == 0, timeout=120000)

        temoins = sorted(
            p.name for p in Path(parallele_getter_enrichi.workspace).glob("vu_*"))
        assert temoins == [
            "vu_Lecteur_A_[verifie]",
            "vu_Lecteur_B_[verifie]",
            "vu_Lecteur_C_[verifie]",
        ]
    finally:
        for worker in parallele_getter_enrichi.workers:
            worker.stop()
            worker.wait(10000)
