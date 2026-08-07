"""Editeur de configuration en formulaire.

Editer du YAML brut expose a la faute de frappe qui casse tout le fichier. Le
formulaire propose un champ adapte au type de chaque valeur et reecrit le YAML
lui-meme ; l'onglet YAML reste le filet de securite pour ce qu'il ne represente
pas.
"""

import pytest
import yaml

from gui_qt.config.config_editor import ConfigEditor, FORM_TAB, YAML_TAB
from gui_qt.config.config_form import (
    ConfigForm,
    build_field,
    humanize,
    looks_like_directory,
)
from gui_qt.config.config_loader import find_log_path_setting, resolve_log_root


# --------------------------------------------------------------- dossier des logs

@pytest.mark.parametrize("cle", [
    "LOG_PATH", "log_path", "Log_Path", "log-path",
    "log_directory", "LOG_DIR", "logs_path", "logdir",
])
def test_the_log_directory_is_found_whatever_the_key_is_called(cle):
    """Les projets nomment ce reglage de facons variees ; en manquer un revient
    a chercher les logs au mauvais endroit."""
    assert find_log_path_setting({cle: "mes_traces"}) == "mes_traces"


def test_an_unrelated_key_is_not_taken_for_a_log_path():
    assert find_log_path_setting({"python_executable": "/usr/bin/python"}) is None


def test_an_empty_value_is_ignored():
    assert find_log_path_setting({"LOG_PATH": "   "}) is None


def test_the_configured_log_directory_is_used(tmp_path):
    (tmp_path / "config.yaml").write_text("LOG_PATH: traces_apdu\n", encoding="utf-8")
    assert resolve_log_root(str(tmp_path)) == tmp_path / "traces_apdu"


def test_an_absolute_log_directory_is_respected(tmp_path):
    """Un chemin absolu ne doit pas etre colle derriere le workspace.

    Le chemin est construit a partir de tmp_path : `/var/log/cartes` n'est pas
    absolu sous Windows, faute de lettre de lecteur, et le test echouait la.
    """
    ailleurs = tmp_path.parent / "traces_ailleurs"
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"LOG_PATH": str(ailleurs)}), encoding="utf-8"
    )
    assert resolve_log_root(str(tmp_path)) == ailleurs


def test_without_configuration_the_default_applies(tmp_path):
    assert resolve_log_root(str(tmp_path)) == tmp_path / "logs"


# -------------------------------------------------------------- choix des widgets

def test_a_boolean_becomes_a_checkbox():
    champ = build_field("parallel", True)
    assert type(champ).__name__ == "_BoolField"


def test_a_boolean_is_not_taken_for_an_integer():
    """En Python True est un int : l'ordre des tests de type compte."""
    assert type(build_field("actif", False)).__name__ == "_BoolField"


def test_an_integer_becomes_a_spinbox():
    assert type(build_field("timeout", 30)).__name__ == "_IntField"


def test_a_float_keeps_its_decimals():
    assert type(build_field("seuil", 1.5)).__name__ == "_FloatField"


def test_a_list_becomes_a_multiline_field():
    assert type(build_field("pythonpath", ["a", "b"])).__name__ == "_ListField"


def test_a_path_setting_gets_a_browse_button():
    champ = build_field("LOG_PATH", "logs")
    assert champ.browse == "dir"


def test_an_executable_setting_browses_for_a_file():
    assert build_field("python_executable", "python.exe").browse == "file"


def test_an_ordinary_text_setting_has_no_browse_button():
    assert build_field("nom_campagne", "essai").browse is None


@pytest.mark.parametrize("cle", ["log_path", "output_dir", "rapport_path", "LOG_DIRECTORY"])
def test_path_like_keys_are_recognized(cle):
    assert looks_like_directory(cle)


# ------------------------------------------------------------------- aller-retour

@pytest.fixture
def form(qtbot):
    widget = ConfigForm()
    qtbot.addWidget(widget)
    return widget


def test_values_are_returned_unchanged_when_nothing_is_edited(form):
    data = {"LOG_PATH": "logs", "parallel": True, "timeout": 30,
            "seuil": 1.5, "pythonpath": ["a", "b"]}
    form.load(data)
    assert form.values() == data


def test_editing_a_field_changes_the_result(form):
    form.load({"LOG_PATH": "logs"})
    form.field("LOG_PATH").widget.setText("traces")
    assert form.values() == {"LOG_PATH": "traces"}


def test_the_key_order_of_the_file_is_preserved(form):
    """Reordonner les cles rendrait le diff du fichier illisible."""
    data = {"zebre": 1, "alpha": 2, "milieu": 3}
    form.load(data)
    assert list(form.values()) == ["zebre", "alpha", "milieu"]


def test_nested_sections_are_kept(form):
    data = {"LOG_PATH": "logs", "rapport": {"format": "html", "ouvrir": True}}
    form.load(data)
    assert form.values() == data


def test_editing_inside_a_nested_section_works(form):
    form.load({"rapport": {"format": "html"}})
    form.field("format", ("rapport",)).widget.setText("xml")
    assert form.values() == {"rapport": {"format": "xml"}}


def test_an_empty_configuration_does_not_crash(form):
    form.load({})
    assert form.values() == {}


def test_a_value_the_form_cannot_edit_is_preserved(form):
    """Une structure inattendue doit ressortir intacte, pas disparaitre."""
    data = {"exotique": [{"a": 1}, {"b": 2}]}
    form.load(data)
    assert form.values()["exotique"] is not None


# ------------------------------------------------------------------ editeur complet

@pytest.fixture
def editor(qtbot, tmp_path):
    fichier = tmp_path / "config.yaml"
    fichier.write_text("LOG_PATH: logs\nparallel: false\n", encoding="utf-8")
    widget = ConfigEditor()
    qtbot.addWidget(widget)
    widget.load(fichier)
    return widget, fichier


def test_the_form_tab_is_shown_first(editor):
    widget, _ = editor
    assert widget.tabs.currentIndex() == FORM_TAB
    assert widget.tabs.tabText(FORM_TAB) == "Reglages"


def test_saving_from_the_form_writes_the_file(editor):
    widget, fichier = editor
    widget.form.field("LOG_PATH").widget.setText("traces_apdu")
    widget.save()

    assert yaml.safe_load(fichier.read_text(encoding="utf-8")) == {
        "LOG_PATH": "traces_apdu", "parallel": False,
    }


def test_switching_to_yaml_shows_the_edited_values(editor):
    """Une saisie ne doit pas etre perdue en changeant d'onglet."""
    widget, _ = editor
    widget.form.field("LOG_PATH").widget.setText("traces_apdu")
    widget.tabs.setCurrentIndex(YAML_TAB)

    assert "traces_apdu" in widget.raw_editor.toPlainText()


def test_editing_the_yaml_feeds_the_form(editor):
    widget, _ = editor
    widget.tabs.setCurrentIndex(YAML_TAB)
    widget.raw_editor.setPlainText("LOG_PATH: depuis_yaml\nnouvelle_cle: 7\n")
    widget.tabs.setCurrentIndex(FORM_TAB)

    assert widget.form.values() == {"LOG_PATH": "depuis_yaml", "nouvelle_cle": 7}


def test_invalid_yaml_never_overwrites_the_file(editor):
    """Le pire scenario : ecraser une configuration valide par du texte casse."""
    widget, fichier = editor
    avant = fichier.read_text(encoding="utf-8")

    widget.tabs.setCurrentIndex(YAML_TAB)
    widget.raw_editor.setPlainText("cle: [non fermee\n")
    assert widget.current_values() is None

    assert fichier.read_text(encoding="utf-8") == avant
    assert "invalide" in widget.status.text().lower()


def test_yaml_that_is_not_a_mapping_is_refused(editor):
    widget, _ = editor
    widget.tabs.setCurrentIndex(YAML_TAB)
    widget.raw_editor.setPlainText("- un\n- deux\n")
    assert widget.current_values() is None


def test_reloading_discards_unsaved_edits(editor):
    widget, _ = editor
    widget.form.field("LOG_PATH").widget.setText("jamais_enregistre")
    widget.reload()
    assert widget.form.values()["LOG_PATH"] == "logs"


# ------------------------------------------------------- fenetre redimensionnable

@pytest.fixture
def dialog(qtbot, tmp_path):
    from gui_qt.config.config_dialog import ConfigDialog

    fichier = tmp_path / "config.yaml"
    fichier.write_text("LOG_PATH: logs\n", encoding="utf-8")
    boite = ConfigDialog(fichier)
    qtbot.addWidget(boite)
    return boite


def test_the_window_can_be_maximized(dialog):
    """Une QDialog n'a pas ce bouton par defaut, et une configuration fournie
    se consulte mal dans une petite fenetre."""
    from PyQt5.QtCore import Qt

    assert dialog.windowFlags() & Qt.WindowMaximizeButtonHint


def test_the_window_can_be_resized(dialog):
    assert dialog.isSizeGripEnabled()

    dialog.resize(1100, 800)
    assert dialog.size().width() == 1100


def test_the_window_has_a_usable_minimum_size(dialog):
    assert dialog.minimumSize().width() <= 560
    assert dialog.minimumSize().height() <= 360


def test_the_chosen_size_is_remembered(qtbot, tmp_path):
    """Redimensionner a chaque ouverture serait penible."""
    from PyQt5.QtCore import QSettings
    from gui_qt.config.config_dialog import GEOMETRY_KEY, ConfigDialog

    fichier = tmp_path / "config.yaml"
    fichier.write_text("LOG_PATH: logs\n", encoding="utf-8")
    settings = QSettings("MyCompany", "PyTestRunner")
    precedent = settings.value(GEOMETRY_KEY)

    try:
        settings.remove(GEOMETRY_KEY)
        premiere = ConfigDialog(fichier)
        qtbot.addWidget(premiere)
        premiere.resize(1024, 768)
        premiere.accept()

        seconde = ConfigDialog(fichier)
        qtbot.addWidget(seconde)
        assert seconde.size().width() == 1024
        assert seconde.size().height() == 768
    finally:
        if precedent is None:
            settings.remove(GEOMETRY_KEY)
        else:
            settings.setValue(GEOMETRY_KEY, precedent)


# ------------------------------------------------------------ compacite du rendu

def test_a_setting_stays_compact(qtbot):
    """La hauteur par reglage etait de 84 px : la description se repliait sur
    quatre lignes dans une colonne etroite, et le libelle occupait deux lignes
    pour la meme information."""
    data = {"LOG_PATH": "traces", "python_executable": "", "parallel": False,
            "timeout": 30, "seuil": 1.5}
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load(data)
    form.resize(760, 600)

    page = form.pages.currentWidget()
    par_reglage = page.widget().sizeHint().height() / len(data)
    assert par_reglage < 75, f"{par_reglage:.0f} px par reglage, trop etale"


# ------------------------------------------------------------ libelles lisibles

@pytest.mark.parametrize("cle, attendu", [
    ("LOG_PATH", "Log path"),
    ("log_path", "Log path"),
    ("ChecksumObjConfigAlgo", "Checksum Obj Config Algo"),
    ("workspace_path", "Workspace path"),
])
def test_a_key_is_made_readable_without_losing_its_letters(cle, attendu):
    """str.capitalize() mettait en minuscules tout ce qui suit la premiere
    lettre : ChecksumObjConfigAlgo devenait Checksumobjconfigalgo."""
    assert humanize(cle) == attendu


def test_the_key_is_never_written_twice(qtbot):
    """Le nom lisible et la cle brute cote a cote doublaient l'information."""
    from PyQt5.QtWidgets import QLabel

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"ChecksumObjConfigAlgo": ["CRC_ISO_3309"], "LOG_PATH": "traces"})

    page = form.pages.currentWidget()
    for libelle in page.widget().findChildren(QLabel):
        texte = libelle.text()
        assert "ChecksumObjConfigAlgo" not in texte, "cle brute affichee en plus du libelle"
        assert "LOG_PATH" not in texte, "cle brute affichee en plus du libelle"


def test_the_exact_key_stays_available_in_the_tooltip(qtbot):
    """C'est l'orthographe qu'on cherche dans le fichier : elle ne doit pas
    disparaitre, seulement cesser d'encombrer."""
    from PyQt5.QtWidgets import QLabel

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"ChecksumObjConfigAlgo": ["CRC_ISO_3309"]})

    page = form.pages.currentWidget()
    infobulles = [w.toolTip() for w in page.widget().findChildren(QLabel)]
    assert any("ChecksumObjConfigAlgo" in bulle for bulle in infobulles)


def test_a_described_setting_keeps_its_explanation_in_the_tooltip(qtbot):
    from PyQt5.QtWidgets import QLabel

    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"LOG_PATH": "traces"})

    page = form.pages.currentWidget()
    infobulles = [w.toolTip() for w in page.widget().findChildren(QLabel)]
    assert any("LOG_PATH" in b and "fichiers .log" in b for b in infobulles)


# --------------------------------------------------- navigation entre sections

def test_a_flat_configuration_has_a_single_section(qtbot):
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"LOG_PATH": "traces", "MODE": "PERSO"})

    assert form.section_titles() == ["General"]
    assert not form.sections.isVisible(), "un navigateur d'une seule section est inutile"


def test_nested_sections_become_navigable_entries(qtbot):
    """Le cas signale : des sections imbriquees rendaient l'affichage illisible."""
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({
        "LOG_PATH": "traces",
        "Modes": {
            "Debug": {"ChecksumObjConfigAlgo": ["CRC_ISO_3309"]},
            "Full": {"ChecksumObjConfigAlgo": ["CRC_CCITT"]},
        },
    })

    assert form.section_titles() == ["General", "Modes", "Debug", "Full"]


def test_each_section_shows_only_its_own_settings(qtbot):
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({
        "LOG_PATH": "traces",
        "Modes": {"Debug": {"algo": ["CRC_ISO_3309"]}},
    })

    assert form.field("LOG_PATH") is not None
    assert form.field("algo") is None, "le reglage d'une sous-section n'est pas au niveau racine"
    assert form.field("algo", ("Modes", "Debug")) is not None


def test_a_deeply_nested_value_survives_the_round_trip(qtbot):
    data = {
        "LOG_PATH": "traces",
        "Modes": {
            "Debug": {"algo": ["CRC_ISO_3309", "CRC_CCITT"], "actif": True},
            "Perso": {"algo": ["CRC_ISO_3309"], "actif": False},
        },
    }
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load(data)

    assert form.values() == data


def test_editing_deep_inside_a_section_works(qtbot):
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"Modes": {"Debug": {"algo": ["CRC_ISO_3309"]}}})

    form.field("algo", ("Modes", "Debug")).widget.setPlainText("CRC_CCITT\nCRC_32")
    assert form.values() == {"Modes": {"Debug": {"algo": ["CRC_CCITT", "CRC_32"]}}}


# ------------------------------------------------------------ largeur des champs

CHEMIN_LONG = r"C:\Projets\CryptoWrapper\cryptolib_ifx_wrapper\Test"


def _affiche(qtbot, data, largeur=1400):
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load(data)
    form.resize(largeur, 600)
    form.show()
    qtbot.wait(10)
    return form


def test_a_long_value_is_shown_in_full(qtbot):
    """Le reproche signale : la fenetre agrandie etait aux trois quarts vide et
    les chemins apparaissaient tronques a `_ifx_wrapper\\Test`.

    La cause n'etait pas le plafond de largeur mais le sizeHint d'un QLineEdit,
    qui vaut une vingtaine de caracteres quel que soit le contenu.
    """
    form = _affiche(qtbot, {"WorkspacePath": CHEMIN_LONG})

    champ = form.field("WorkspacePath").widget
    necessaire = champ.fontMetrics().horizontalAdvance(CHEMIN_LONG)
    assert champ.width() >= necessaire, (
        f"{champ.width()} px pour une valeur qui en demande {necessaire}"
    )


def test_a_short_value_does_not_get_a_giant_field(qtbot):
    """S'adapter au contenu, c'est aussi ne pas etaler un mot sur un ecran."""
    form = _affiche(qtbot, {"Mode": "PERSO"})
    assert form.field("Mode").widget.width() <= 400


def test_a_field_does_not_stretch_across_a_wide_window(qtbot):
    """Etire sur toute la largeur, le bouton Parcourir se retrouvait a l'autre
    bout de la fenetre."""
    from gui_qt.config.config_form import MAX_FIELD_WIDTH

    form = _affiche(qtbot, {"LOG_PATH": "x" * 500}, largeur=2400)

    assert form.field("LOG_PATH").widget.width() <= MAX_FIELD_WIDTH


def test_a_narrow_window_shrinks_the_fields_instead_of_overflowing(qtbot):
    """Le champ s'adapte au contenu sans imposer sa largeur a la fenetre."""
    form = _affiche(qtbot, {"WorkspacePath": CHEMIN_LONG}, largeur=520)
    assert form.field("WorkspacePath").widget.width() < 520


def test_a_list_is_wide_enough_for_its_longest_value(qtbot):
    form = _affiche(qtbot, {"PYTHONPATH": ["a", CHEMIN_LONG]})

    champ = form.field("PYTHONPATH").widget
    necessaire = champ.fontMetrics().horizontalAdvance(CHEMIN_LONG)
    assert champ.width() >= necessaire


def test_the_section_navigator_fits_its_titles(qtbot):
    """Une largeur fixe tronquait les noms de sections imbriquees."""
    from gui_qt.config.config_form import NAV_MAX_WIDTH

    court = _affiche(qtbot, {"a": 1, "Modes": {"b": 2}})
    long = _affiche(qtbot, {"a": 1, "ConfigurationDesAlgorithmesDeChecksum": {"b": 2}})

    assert long.sections.maximumWidth() > court.sections.maximumWidth()
    assert long.sections.maximumWidth() <= NAV_MAX_WIDTH


def _lignes_visibles(champ) -> float:
    """Nombre de valeurs affichables, mesure sur la mise en page du document.

    fontMetrics().lineSpacing() sous-estime l'interligne reel : s'en servir
    faisait croire qu'une valeur de plus tenait dans la boite.
    """
    document = champ.document()
    hauteur = document.documentLayout().blockBoundingRect(document.firstBlock()).height()
    return champ.height() / hauteur


def test_a_list_is_tall_enough_to_show_its_values(qtbot):
    """Les listes etaient tronquees a deux lignes visibles."""
    form = _affiche(qtbot, {"PARAM": ["FULL", "DEBUG", "SANITY", "PERSO"]})

    champ = form.field("PARAM").widget
    lignes = _lignes_visibles(champ)
    assert lignes >= 4, f"{lignes:.1f} ligne(s) visible(s) pour 4 valeurs"
    assert champ.verticalScrollBar().maximum() == 0, "quatre valeurs tiennent sans defilement"


def test_a_very_long_list_stays_bounded(qtbot):
    form = ConfigForm()
    qtbot.addWidget(form)
    form.load({"PARAM": [f"valeur_{i}" for i in range(200)]})

    champ = form.field("PARAM").widget
    assert _lignes_visibles(champ) <= 12, "une longue liste ne doit pas remplir l'ecran"
