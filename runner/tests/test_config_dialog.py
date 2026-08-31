"""L'editeur de configuration, du champ affiche au fichier ecrit.

Le formulaire evite d'avoir a connaitre la syntaxe YAML pour changer un
lecteur. Ce qu'on lui demande surtout, c'est de ne pas abimer le fichier au
passage : la promesse tenue par `runner.domain.config_file` ne vaut que si le
dialogue ne lui envoie effectivement que ce qui a change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
)

from runner.domain.config_file import charger
from runner.ui.config_dialog import ONGLET_YAML, ConfigDialog, ReaderList

CONFIG = """\
# La campagne de reference.
Reader: Cosmo11Secured Reader   # ne pas committer un lecteur personnel
Readers:
  - TestBiosWrapperTU Reader
LOG_PATH: traces_apdu
title: "Campagne 2026"
timeout: 30
verbose: false

campaign:
  timeout: 300
"""


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fichier(tmp_path):
    chemin = tmp_path / "config.yml"
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(CONFIG)
    return chemin


@pytest.fixture
def dialogue(qapp, fichier):
    return ConfigDialog(str(fichier), ["Cosmo11Secured Reader", "Un Autre Reader"])


def _champ(dialogue, *chemin):
    for c in dialogue._champs:
        if c.chemin == chemin:
            return c
    raise AssertionError(f"aucun champ pour {chemin} ; "
                         f"connus : {[c.chemin for c in dialogue._champs]}")


# ------------------------------------------------------------- le formulaire

def test_every_setting_of_the_file_gets_a_field(dialogue):
    chemins = {c.chemin for c in dialogue._champs}
    assert chemins == {("Reader",), ("Readers",), ("LOG_PATH",), ("title",),
                       ("timeout",), ("verbose",), ("campaign", "timeout")}


def test_a_setting_in_a_section_keeps_its_path(dialogue):
    """Deux `timeout` dans le fichier : sans le chemin, enregistrer l'un
    ecraserait l'autre."""
    assert _champ(dialogue, "timeout").depart == 30
    assert _champ(dialogue, "campaign", "timeout").depart == 300


@pytest.mark.parametrize("chemin, classe", [
    (("verbose",), QCheckBox),
    (("timeout",), QSpinBox),
    (("Readers",), ReaderList),
    (("Reader",), QComboBox),
    (("LOG_PATH",), QLineEdit),
])
def test_the_widget_matches_the_type_of_the_value(dialogue, chemin, classe):
    """Une case a cocher pour un booleen : taper « flase » dans une zone de
    texte est une erreur qu'un widget adapte rend impossible."""
    widget = _champ(dialogue, *chemin).widget
    if isinstance(widget, classe):
        return
    # Les chemins recoivent un bouton « Parcourir » : le champ est alors dans
    # une boite avec lui.
    assert widget.findChildren(classe), f"{chemin} : {type(widget).__name__}"


def test_an_empty_setting_shows_an_empty_field(qapp, tmp_path):
    """`cle:` sans rien derriere se lit None. Rendu tel quel, le champ
    affichait le mot « None » -- que rien ne distingue d'une valeur voulue, et
    qui serait ecrit dans le fichier a l'enregistrement."""
    chemin = tmp_path / "config.yml"
    chemin.write_text("python_executable:\nReader: A\n", encoding="utf-8")
    dialogue = ConfigDialog(str(chemin))

    champ = _champ(dialogue, "python_executable")
    assert champ.depart == ""
    assert "None" not in champ.widget.findChild(QLineEdit).text()


def test_a_path_setting_offers_to_browse(dialogue):
    widget = _champ(dialogue, "LOG_PATH").widget
    boutons = [b for b in widget.findChildren(type(dialogue.save_button))
               if "Browse" in b.text()]
    assert boutons, "taper un chemin a la main est la premiere source d'erreur"


def test_the_reader_field_offers_the_readers_we_know(dialogue):
    combo = _champ(dialogue, "Reader").widget
    proposes = [combo.itemText(i) for i in range(combo.count())]
    assert "Un Autre Reader" in proposes
    # Le lecteur en cours reste choisissable meme debranche, sinon rouvrir la
    # configuration ferait disparaitre le reglage.
    assert "Cosmo11Secured Reader" in proposes
    assert combo.currentText() == "Cosmo11Secured Reader"


# ------------------------------------------------------------ enregistrement

def test_saving_without_a_change_leaves_the_file_alone(dialogue, fichier):
    """Le fichier ne doit pas bouger d'un octet : rouvrir la configuration et
    cliquer Save par reflexe ne doit rien reecrire."""
    avant = fichier.read_bytes()
    dialogue.save()

    assert fichier.read_bytes() == avant
    assert "Nothing to save" in dialogue.status.text()


def test_only_the_changed_setting_reaches_the_file(dialogue, fichier):
    """Renvoyer TOUS les champs reecrirait aussi les lignes intactes.

    Le plus souvent la ligne reecrite tombe a l'identique, et rien ne se voit.
    Pas toujours : `title: "Campagne 2026"` n'a besoin d'aucun guillemet pour
    rester du YAML valide, donc la reecrire la depouille. Le fichier reste
    correct et n'est plus celui qu'on avait ecrit -- exactement ce que cet
    editeur promet d'eviter.
    """
    avant = fichier.read_text(encoding="utf-8").splitlines()
    _champ(dialogue, "LOG_PATH").widget.findChild(QLineEdit).setText("ailleurs")
    dialogue.save()

    apres = fichier.read_text(encoding="utf-8").splitlines()
    differentes = [i for i, (a, b) in enumerate(zip(avant, apres)) if a != b]
    assert len(differentes) == 1, (
        "lignes touchees : " + " | ".join(apres[i] for i in differentes))
    assert charger(fichier)["LOG_PATH"] == "ailleurs"
    assert 'title: "Campagne 2026"' in fichier.read_text(encoding="utf-8")


def test_the_comments_are_still_there_after_saving(dialogue, fichier):
    """C'est tout l'interet de ne pas passer par un safe_dump."""
    _champ(dialogue, "timeout").widget.setValue(60)
    dialogue.save()

    texte = fichier.read_text(encoding="utf-8")
    assert "# La campagne de reference." in texte
    assert "# ne pas committer un lecteur personnel" in texte


def test_a_section_setting_is_saved_where_it_belongs(dialogue, fichier):
    _champ(dialogue, "campaign", "timeout").widget.setValue(600)
    dialogue.save()

    donnees = charger(fichier)
    assert donnees["campaign"]["timeout"] == 600
    assert donnees["timeout"] == 30, "le reglage de la racine a ete ecrase"


def test_a_plain_list_is_still_a_text_box(qapp, tmp_path):
    """Seuls les lecteurs ont droit a leur liste : les autres reglages a
    valeurs multiples restent une zone de texte, une par ligne."""
    chemin = tmp_path / "config.yml"
    chemin.write_text("pythonpath:\n  - src\n", encoding="utf-8")
    dialogue = ConfigDialog(str(chemin))

    champ = _champ(dialogue, "pythonpath")
    assert isinstance(champ.widget, QPlainTextEdit)
    champ.widget.setPlainText("src\nlib\n")
    dialogue.save()

    assert charger(chemin)["pythonpath"] == ["src", "lib"]


def test_a_checkbox_saves_a_real_boolean(dialogue, fichier):
    _champ(dialogue, "verbose").widget.setChecked(True)
    dialogue.save()

    assert charger(fichier)["verbose"] is True


def test_saving_twice_does_not_write_twice(dialogue, fichier):
    """Apres enregistrement les champs repartent de la valeur du fichier :
    sans cela le deuxieme Save renverrait les memes modifications."""
    _champ(dialogue, "timeout").widget.setValue(60)
    dialogue.save()
    avant = fichier.read_bytes()

    dialogue.save()
    assert fichier.read_bytes() == avant
    assert "Nothing to save" in dialogue.status.text()


# ----------------------------------------------------------------- onglet YAML

def test_the_yaml_tab_shows_the_file_as_it_is(dialogue, fichier):
    """Y afficher ce que le formulaire a en memoire donnerait un texte
    reserialise, commentaires effaces -- exactement ce qu'on evite."""
    assert dialogue.raw.toPlainText() == fichier.read_text(encoding="utf-8")


def test_the_yaml_tab_saves_what_you_typed(dialogue, fichier):
    dialogue.tabs.setCurrentIndex(ONGLET_YAML)
    dialogue.raw.setPlainText("# tout neuf\nReader: X\n")
    dialogue.save()

    assert fichier.read_text(encoding="utf-8") == "# tout neuf\nReader: X\n"


def test_broken_yaml_is_refused_and_the_file_untouched(dialogue, fichier):
    """Un fichier invalide rend le workspace incollectable, et l'erreur
    ressortirait bien plus tard, sous la forme d'une collecte qui echoue sans
    raison apparente."""
    avant = fichier.read_bytes()
    dialogue.tabs.setCurrentIndex(ONGLET_YAML)
    dialogue.raw.setPlainText("Reader: [pas ferme\n")
    dialogue.save()

    assert fichier.read_bytes() == avant
    assert "Not saved" in dialogue.status.text()


def test_unsaved_form_changes_are_flagged_when_leaving_for_the_yaml(dialogue):
    """Elles ne sont PAS recopiees dans l'onglet YAML -- ce serait reserialiser
    le fichier. On le dit plutot que de laisser croire qu'elles y sont."""
    _champ(dialogue, "timeout").widget.setValue(60)
    dialogue.tabs.setCurrentIndex(ONGLET_YAML)

    assert "Unsaved changes in the form" in dialogue.status.text()


def test_switching_tabs_with_nothing_pending_says_nothing(dialogue):
    dialogue.tabs.setCurrentIndex(ONGLET_YAML)
    assert dialogue.status.text() == ""


# ------------------------------------------------------------------ recharger

def test_reloading_picks_up_a_change_made_outside(dialogue, fichier):
    with open(fichier, "a", encoding="utf-8", newline="") as f:
        f.write("nouveau: 1\n")
    dialogue.reload()

    assert _champ(dialogue, "nouveau").depart == 1


def test_a_file_with_no_setting_says_so(qapp, tmp_path):
    chemin = tmp_path / "config.yml"
    chemin.write_text("# rien encore\n", encoding="utf-8")
    dialogue = ConfigDialog(str(chemin))

    assert dialogue._champs == []
    textes = [w.text() for w in dialogue.form_host.findChildren(type(dialogue.status))]
    assert any("no setting" in texte for texte in textes)


# ------------------------------------------------------- place dans la fenetre

@pytest.fixture
def fenetre(qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def _hauteur(fenetre, widget) -> int:
    return widget.mapTo(fenetre, widget.rect().topLeft()).y()


def test_the_run_actions_have_a_row_of_their_own(fenetre):
    """Ils etaient a l'autre bout de la barre du workspace : on cochait des
    tests a gauche, puis on traversait toute la fenetre pour les lancer.

    Les mettre en tete de cette meme barre les rapprochait, mais les melait au
    chemin du workspace -- qu'on ne touche qu'une fois par session. Une rangee
    a eux repond aux deux : a portee, et sans confusion sur ce qui agit.
    """
    barre = fenetre.run_button.parentWidget().layout()
    dedans = {barre.itemAt(i).widget() for i in range(barre.count())}

    assert {fenetre.run_button, fenetre.stop_button, fenetre.rerun_button} <= dedans
    assert fenetre.workspace_combo not in dedans
    assert fenetre.load_button not in dedans


def test_the_run_row_sits_between_the_workspace_and_the_tree(fenetre):
    fenetre.show()
    try:
        assert (_hauteur(fenetre, fenetre.workspace_combo)
                < _hauteur(fenetre, fenetre.run_button)
                < _hauteur(fenetre, fenetre.search))
    finally:
        fenetre.hide()


def test_the_history_button_is_reachable_without_a_menu(fenetre):
    barre = fenetre.load_button.parentWidget().layout()
    dans_la_barre = {barre.itemAt(i).widget() for i in range(barre.count())}
    assert fenetre.history_button in dans_la_barre


def test_the_config_button_sits_with_the_workspace_controls(fenetre):
    """La configuration decrit CE dossier -- ses lecteurs, ses logs, son
    interpreteur. Sa place est dans le groupe qui parle du workspace, pas
    avec Re-run / Stop / Run qui parlent du prochain run."""
    barre = fenetre.load_button.parentWidget().layout()
    positions = {barre.itemAt(i).widget(): i for i in range(barre.count())
                 if barre.itemAt(i).widget() is not None}

    assert positions[fenetre.config_button] == positions[fenetre.load_button] + 1
    assert positions[fenetre.config_button] > positions[fenetre.workspace_combo]
    # Les actions de run ne partagent plus cette barre du tout.
    assert fenetre.run_button not in positions


def test_the_config_button_is_off_without_a_workspace(fenetre):
    assert not fenetre.config_button.isEnabled()


def test_the_window_is_named_pytest_runner(fenetre):
    assert fenetre.windowTitle() == "Pytest Runner"


def test_the_config_button_is_on_even_when_no_yaml_was_detected(fenetre, tmp_path):
    from runner.domain.workspace import Workspace

    fenetre.workspace = Workspace(str(tmp_path), "", {})
    fenetre._update_actions()

    assert fenetre.config_button.isEnabled()
    assert fenetre.act_config.isEnabled()


def test_the_theme_button_is_not_in_the_row_of_run_actions(fenetre):
    """Pose entre l'espace elastique et Re-run, il s'alignait avec les boutons
    de run et se lisait comme une quatrieme action -- alors que c'est un
    reglage de confort."""
    from PySide6.QtCore import Qt

    barre = fenetre.run_button.parentWidget().layout()
    dans_la_barre = {barre.itemAt(i).widget() for i in range(barre.count())}

    assert fenetre.theme_button not in dans_la_barre
    assert fenetre.menuBar().cornerWidget(Qt.TopRightCorner) is fenetre.theme_button


# ------------------------------------------------- choisir le fichier a lire

DEUXIEME = "Reader: Un Autre Reader\nLOG_PATH: ailleurs\n"


@pytest.fixture
def deux_fichiers(tmp_path):
    """Un workspace avec deux YAML : l'exemple, et celui de la campagne."""
    (tmp_path / "config.yaml").write_text(DEUXIEME, encoding="utf-8")
    campagne = tmp_path / "campagne.yml"
    with open(campagne, "w", encoding="utf-8", newline="") as f:
        f.write(CONFIG)
    return tmp_path


def test_the_first_file_found_is_not_always_the_right_one(deux_fichiers):
    """Le defaut signale : deux YAML, et l'outil en prend un sans le dire.

    `config.yaml` porte un nom standard, il passe donc devant -- meme quand
    c'est un exemple et que la vraie campagne est ailleurs. Tout en decoule :
    les lecteurs, le dossier de logs, l'interpreteur.
    """
    from runner.domain.workspace import Workspace

    auto = Workspace.load(str(deux_fichiers))
    assert auto.config_path.endswith("config.yaml")
    assert [r.name for r in auto.readers] == ["Un Autre Reader"]

    choisi = Workspace.load(str(deux_fichiers), "campagne.yml")
    assert choisi.config_path.endswith("campagne.yml")
    assert [r.name for r in choisi.readers] == ["Cosmo11Secured Reader",
                                                "TestBiosWrapperTU Reader"]


def test_a_chosen_file_that_disappeared_falls_back(deux_fichiers):
    """Renomme ou supprime entre deux sessions : mieux vaut la detection qu'un
    workspace sans aucun reglage."""
    from runner.domain.workspace import Workspace

    espace = Workspace.load(str(deux_fichiers), "efface.yml")
    assert espace.config_path.endswith("config.yaml")


def test_an_absolute_choice_works_too(deux_fichiers):
    from runner.domain.workspace import Workspace

    espace = Workspace.load(str(deux_fichiers),
                            str(deux_fichiers / "campagne.yml"))
    assert espace.config_path.endswith("campagne.yml")


def _dialogue_deux(qapp, deux_fichiers, courant="campagne.yml"):
    from runner.domain.workspace import fichiers_config

    return ConfigDialog(
        str(deux_fichiers / courant), ["Cosmo11Secured Reader"],
        candidats=[str(c) for c in fichiers_config(str(deux_fichiers))],
        workspace_path=str(deux_fichiers))


def test_the_file_picker_is_available_even_with_one_detected_file(qapp, fichier):
    """Le fichier voulu peut etre dans un sous-dossier non detecte."""
    dialogue = ConfigDialog(str(fichier), candidats=[str(fichier)])

    assert not dialogue.file_row.isHidden()
    assert dialogue.choose_file_button.isEnabled()


def test_browse_can_choose_a_yaml_in_a_subfolder(qapp, tmp_path, monkeypatch):
    racine = tmp_path / "config.yml"
    racine.write_text("Reader: Root\n", encoding="utf-8")
    dossier = tmp_path / ".Campaign"
    dossier.mkdir()
    imbrique = dossier / "campaign.yml"
    imbrique.write_text("Reader: Nested\n", encoding="utf-8")
    dialogue = ConfigDialog(str(racine), candidats=[str(racine)],
                            workspace_path=str(tmp_path))
    monkeypatch.setattr(
        "runner.ui.config_dialog.QFileDialog.getOpenFileName",
        lambda *_args: (str(imbrique), "YAML files (*.yml *.yaml)"))

    dialogue.choose_file_button.click()

    assert dialogue.path == imbrique
    assert dialogue.file_combo.currentText() == ".Campaign/campaign.yml"
    assert _champ(dialogue, "Reader").depart == "Nested"


def test_choosing_the_first_config_remembers_its_relative_subfolder(
        fenetre, tmp_path, monkeypatch):
    from runner.domain.workspace import Workspace

    dossier = tmp_path / ".Campaign"
    dossier.mkdir()
    config = dossier / "campaign.yml"
    config.write_text("Reader: Nested\n", encoding="utf-8")
    # Force le cas signale : workspace deja charge mais aucun YAML retenu.
    fenetre.workspace = Workspace(str(tmp_path), "", {})
    fenetre._update_actions()
    monkeypatch.setattr(
        "runner.ui.main_window.QFileDialog.getOpenFileName",
        lambda *_args: (str(config), "YAML files (*.yml *.yaml)"))
    monkeypatch.setattr("runner.ui.config_dialog.ConfigDialog.exec_", lambda _self: 0)
    recharges = []
    monkeypatch.setattr(fenetre, "load_workspace", lambda: recharges.append(True))

    fenetre.open_config_dialog()

    assert fenetre._config_retenue(str(tmp_path)) == str(
        Path(".Campaign") / "campaign.yml")
    assert Path(fenetre.workspace.config_path) == config
    assert recharges == [True]


def test_the_picker_starts_on_the_file_being_edited(qapp, deux_fichiers):
    dialogue = _dialogue_deux(qapp, deux_fichiers)
    assert dialogue.file_combo.currentText() == "campagne.yml"


def test_switching_file_reloads_the_form(qapp, deux_fichiers):
    dialogue = _dialogue_deux(qapp, deux_fichiers)
    assert _champ(dialogue, "LOG_PATH").depart == "traces_apdu"

    position = dialogue.file_combo.findText("config.yaml")
    dialogue.file_combo.setCurrentIndex(position)

    assert dialogue.path.name == "config.yaml"
    assert _champ(dialogue, "LOG_PATH").depart == "ailleurs"


def test_switching_file_says_what_it_dropped(qapp, deux_fichiers):
    """Les emporter vers l'autre fichier ecrirait des reglages la ou ils
    n'appartiennent pas ; les perdre en silence est pire encore."""
    dialogue = _dialogue_deux(qapp, deux_fichiers)
    _champ(dialogue, "timeout").widget.setValue(999)

    dialogue.file_combo.setCurrentIndex(dialogue.file_combo.findText("config.yaml"))

    assert "unsaved change was dropped" in dialogue.status.text()
    assert charger(deux_fichiers / "campagne.yml")["timeout"] == 30


# ------------------------------------------- ajouter et retirer un lecteur

def test_the_extra_readers_are_a_list_you_can_add_to(dialogue):
    from runner.ui.config_dialog import ReaderList

    champ = _champ(dialogue, "Readers")
    assert isinstance(champ.widget, ReaderList)
    assert champ.widget.valeurs() == ["TestBiosWrapperTU Reader"]


def test_adding_a_reader_offers_one_we_know(dialogue, fichier):
    """Retaper un nom long est l'occasion d'une faute qui rend le run muet."""
    liste = _champ(dialogue, "Readers").widget
    liste.ajouter()

    assert liste.valeurs() == ["TestBiosWrapperTU Reader", "Cosmo11Secured Reader"]
    dialogue.save()
    assert charger(fichier)["Readers"] == ["TestBiosWrapperTU Reader",
                                           "Cosmo11Secured Reader"]


def test_removing_a_reader_takes_it_out_of_the_file(dialogue, fichier):
    liste = _champ(dialogue, "Readers").widget
    liste.list.setCurrentRow(0)
    liste.retirer()
    dialogue.save()

    assert charger(fichier)["Readers"] == []


def test_the_main_reader_is_never_touched(dialogue, fichier):
    """`Reader` est le lecteur que les tests lisent aujourd'hui : ajouter ou
    retirer dans la liste ne doit jamais y toucher."""
    liste = _champ(dialogue, "Readers").widget
    liste.ajouter()
    liste.list.setCurrentRow(0)
    liste.retirer()
    dialogue.save()

    assert charger(fichier)["Reader"] == "Cosmo11Secured Reader"


def test_a_blank_entry_never_reaches_the_file(dialogue, fichier):
    """Elle donnerait une ligne `- ""` et un run sur un lecteur sans nom."""
    liste = _champ(dialogue, "Readers").widget
    liste._ajouter_entree("   ")
    dialogue.save()

    assert charger(fichier)["Readers"] == ["TestBiosWrapperTU Reader"]


def test_remove_is_off_until_something_is_selected(dialogue):
    liste = _champ(dialogue, "Readers").widget
    assert not liste.remove_button.isEnabled()

    liste.list.setCurrentRow(0)
    assert liste.remove_button.isEnabled()
