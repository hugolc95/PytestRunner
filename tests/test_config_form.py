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
    (tmp_path / "config.yaml").write_text("LOG_PATH: /var/log/cartes\n", encoding="utf-8")
    from pathlib import Path
    assert resolve_log_root(str(tmp_path)) == Path("/var/log/cartes")


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


def test_labels_are_readable():
    assert humanize("log_path") == "Log path"


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
    form._fields["LOG_PATH"].widget.setText("traces")
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
    form._nested["rapport"]._fields["format"].widget.setText("xml")
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
    widget.form._fields["LOG_PATH"].widget.setText("traces_apdu")
    widget.save()

    assert yaml.safe_load(fichier.read_text(encoding="utf-8")) == {
        "LOG_PATH": "traces_apdu", "parallel": False,
    }


def test_switching_to_yaml_shows_the_edited_values(editor):
    """Une saisie ne doit pas etre perdue en changeant d'onglet."""
    widget, _ = editor
    widget.form._fields["LOG_PATH"].widget.setText("traces_apdu")
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
    widget.form._fields["LOG_PATH"].widget.setText("jamais_enregistre")
    widget.reload()
    assert widget.form.values()["LOG_PATH"] == "logs"
