"""L'editeur de configuration, du champ affiche au fichier ecrit.

Le formulaire evite d'avoir a connaitre la syntaxe YAML pour changer un
lecteur. Ce qu'on lui demande surtout, c'est de ne pas abimer le fichier au
passage : la promesse tenue par `runner.domain.config_file` ne vaut que si le
dialogue ne lui envoie effectivement que ce qui a change.
"""

from __future__ import annotations

import pytest
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
)

from runner.domain.config_file import charger
from runner.ui.config_dialog import ONGLET_YAML, ConfigDialog

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
    from PyQt5.QtWidgets import QApplication

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
    (("Readers",), QPlainTextEdit),
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


def test_a_list_is_saved_line_by_line(dialogue, fichier):
    _champ(dialogue, "Readers").widget.setPlainText("A Reader\nB Reader\n")
    dialogue.save()

    assert charger(fichier)["Readers"] == ["A Reader", "B Reader"]


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

    assert "Unsaved" in dialogue.status.text()


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
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


def test_the_config_button_sits_with_the_workspace_controls(fenetre):
    """La configuration decrit CE dossier -- ses lecteurs, ses logs, son
    interpreteur. Sa place est dans le groupe qui parle du workspace, pas
    avec Re-run / Stop / Run qui parlent du prochain run."""
    barre = fenetre.load_button.parentWidget().layout()
    positions = {barre.itemAt(i).widget(): i for i in range(barre.count())
                 if barre.itemAt(i).widget() is not None}

    assert positions[fenetre.config_button] == positions[fenetre.load_button] + 1
    assert positions[fenetre.config_button] < positions[fenetre.run_button]


def test_the_config_button_is_off_without_a_workspace(fenetre):
    assert not fenetre.config_button.isEnabled()


def test_the_theme_button_is_not_in_the_row_of_run_actions(fenetre):
    """Pose entre l'espace elastique et Re-run, il s'alignait avec les boutons
    de run et se lisait comme une quatrieme action -- alors que c'est un
    reglage de confort."""
    from PyQt5.QtCore import Qt

    barre = fenetre.run_button.parentWidget().layout()
    dans_la_barre = {barre.itemAt(i).widget() for i in range(barre.count())}

    assert fenetre.theme_button not in dans_la_barre
    assert fenetre.menuBar().cornerWidget(Qt.TopRightCorner) is fenetre.theme_button
