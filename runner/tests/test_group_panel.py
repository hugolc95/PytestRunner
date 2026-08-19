"""La fiche d'un regroupement : cliquer un dossier doit dire quelque chose.

Un regroupement n'etait lie a rien : la fiche gardait le test precedent a
l'ecran, et l'on croyait lire le dossier qu'on venait de cliquer. C'est le
defaut que ce qui suit verrouille, en plus du contenu de la nouvelle fiche.
"""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtWidgets import QLabel

from runner.domain.models import Reader, Status
from runner.domain.tree import build_tree

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid[A1]",
    "suite/apdu/test_select.py::test_aid[A2]",
    "suite/perso/test_cert.py::test_chr",
]
LECTEURS = (Reader("Cosmo11Secured Reader", 0), Reader("TestBiosWrapperTU Reader", 1))


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.domain.workspace import Workspace
    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    f.workspace = Workspace.load(str(tmp_path))
    f.model.set_tree(build_tree(NODEIDS))
    f.model.set_readers(LECTEURS)
    f.results.set_readers(LECTEURS)
    f.left_stack.setCurrentWidget(f.tree)
    f.tree.expandAll()
    yield f
    f.settings.clear()
    f.close()
    f.deleteLater()
    qapp.processEvents()


@pytest.fixture
def joue(fenetre):
    """Un run : `test_atr` rouge partout, `test_aid[A2]` rouge sur un lecteur."""
    for nodeid in NODEIDS:
        for lecteur in LECTEURS:
            fenetre.model.apply_outcome(nodeid, Status.PASSED, lecteur.index)
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 0)
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 1)
    fenetre.model.apply_outcome(NODEIDS[2], Status.FAILED, 1)
    return fenetre


def _index(fenetre, *chemin):
    """Descend l'arbre par les noms affiches."""
    index = QModelIndex()
    for nom in chemin:
        for ligne in range(fenetre.model.rowCount(index)):
            candidat = fenetre.model.index(ligne, 0, index)
            if fenetre.model.data(candidat) == nom:
                index = candidat
                break
        else:
            raise AssertionError(f"{nom} introuvable sous {chemin}")
    return index


def _fiche(fenetre):
    return fenetre.results.detail


# ----------------------------------------------------------- quelle fiche

def test_clicking_a_folder_stops_showing_the_previous_test(joue):
    """Le defaut d'origine : la fiche restait sur le test d'avant."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(joue.model.index_for_nodeid(NODEIDS[0]))
    assert fiche.stack.currentIndex() == fiche.PAGE_TEST
    assert fiche.nodeid() == NODEIDS[0]

    joue.tree.setCurrentIndex(_index(joue, "suite", "apdu"))

    assert fiche.stack.currentIndex() == fiche.PAGE_GROUPE
    assert fiche.nodeid() == "", "la fiche se croit encore sur un test"


def test_clicking_a_test_comes_back_to_its_card(joue):
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite"))
    joue.tree.setCurrentIndex(joue.model.index_for_nodeid(NODEIDS[3]))

    assert fiche.stack.currentIndex() == fiche.PAGE_TEST
    assert fiche.nodeid() == NODEIDS[3]


@pytest.mark.parametrize("chemin, nom", [
    (("suite",), "suite"),
    (("suite", "apdu"), "apdu"),
    (("suite", "apdu", "test_select.py"), "test_select.py"),
    (("suite", "apdu", "test_select.py", "test_aid"), "test_aid"),
])
def test_every_kind_of_grouping_gets_a_card(joue, chemin, nom):
    """Dossier, fichier, et test parametre : aucun n'a de nodeid, tous doivent
    repondre."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, *chemin))

    assert fiche.stack.currentIndex() == fiche.PAGE_GROUPE
    assert fiche.group_name.text() == nom


# ------------------------------------------------------------- le contenu

def test_the_card_counts_what_the_node_contains_per_reader(joue):
    joue.tree.setCurrentIndex(_index(joue, "suite", "apdu"))

    compteurs, _ = joue.model.subtree_summary(_index(joue, "suite", "apdu"))
    assert compteurs[0] == {Status.PASSED: 2, Status.FAILED: 1}
    assert compteurs[1] == {Status.PASSED: 1, Status.FAILED: 2}


def test_tests_never_run_are_counted_as_pending(fenetre):
    """Omettre les tests jamais joues ferait une barre pleine et verte sur un
    dossier ou rien n'a tourne."""
    compteurs, echecs = fenetre.model.subtree_summary(_index(fenetre, "suite"))

    assert compteurs[0] == {Status.PENDING: 4}
    assert echecs == []


def test_the_failing_list_has_one_line_per_test(joue):
    """Une ligne par couple test-lecteur affichait deux fois le meme nom des
    qu'un test tombait sur les deux."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite"))

    lignes = [fiche.failures.item(i).text() for i in range(fiche.failures.count())]
    assert len(lignes) == 2, lignes
    assert sum("test_atr" in l for l in lignes) == 1


def test_a_test_failing_on_both_readers_names_them_both(joue):
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite"))

    ligne = [fiche.failures.item(i).text() for i in range(fiche.failures.count())
             if "test_atr" in fiche.failures.item(i).text()][0]
    assert "Cosmo11Secured" in ligne and "TestBiosWrapperTU" in ligne


def test_the_count_says_tests_not_combinations(joue):
    """La barre d'etat compte les couples test-lecteur ; ici on compte des
    tests. Sans le mot, les deux nombres se contrediraient a l'ecran."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite"))

    assert fiche.failures_title.text() == "Failing (2 tests)"


def test_a_clean_node_says_so_instead_of_showing_nothing(joue):
    """Une zone vide se lit comme un affichage qui n'a pas fini."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite", "perso"))

    assert fiche.failures_title.text() == ""
    assert fiche.failures.count() == 1
    assert "Nothing is failing" in fiche.failures.item(0).text()


def test_the_root_shows_no_empty_path_line(joue):
    """Elle prendrait sa hauteur et decalerait le titre sans rien dire."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite"))
    assert fiche.group_path.isHidden()

    joue.tree.setCurrentIndex(_index(joue, "suite", "apdu", "test_select.py"))
    assert not fiche.group_path.isHidden()
    assert fiche.group_path.text() == "suite / apdu"


# --------------------------------------------------------------- naviguer

def test_clicking_a_failure_goes_to_that_test(joue):
    """C'est le geste suivant une fois sur deux, apres avoir vu la liste."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite"))

    item = [fiche.failures.item(i) for i in range(fiche.failures.count())
            if "test_atr" in fiche.failures.item(i).text()][0]
    fiche._sur_echec(item)

    assert fiche.stack.currentIndex() == fiche.PAGE_TEST
    assert fiche.nodeid() == NODEIDS[0]
    assert joue.model.data(joue.tree.currentIndex().siblingAtColumn(0)) == "test_atr"


def test_the_placeholder_line_leads_nowhere(joue):
    """« Nothing is failing » n'est pas un test : cliquer dessus ne doit pas
    tenter d'y aller."""
    fiche = _fiche(joue)
    joue.tree.setCurrentIndex(_index(joue, "suite", "perso"))
    recus = []
    fiche.test_chosen.connect(recus.append)

    fiche._sur_echec(fiche.failures.item(0))
    assert recus == []


# ------------------------------------------------------- les autres onglets

def test_a_group_does_not_leave_the_previous_source_behind(joue, tmp_path):
    """Un dossier n'a pas de fichier de test a ouvrir. Garder celui d'avant
    ferait croire qu'il parle de ce qu'on vient de cliquer.

    La source et le log sont reellement poses sur le disque : sans eux, les
    deux panneaux etaient deja vides et le test ne prouvait rien.
    """
    source = tmp_path / "suite" / "apdu" / "test_select.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def test_atr():\n    assert False\n", encoding="utf-8")

    journal = (tmp_path / "logs" / "20260818"
               / "Cosmo11Secured Reader" / "suite" / "apdu")
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "test_atr.log").write_text("APDU >> 00A4\n", encoding="utf-8")
    joue.results.set_log_root(tmp_path / "logs")

    joue.tree.setCurrentIndex(joue.model.index_for_nodeid(NODEIDS[0]))
    assert "test_atr" in joue.results.source.editor.toPlainText(), (
        "la source n'a pas ete chargee : il n'y aurait rien a effacer")
    assert "APDU" in joue.results.logs.views[0].text(), (
        "le log n'a pas ete charge : il n'y aurait rien a effacer")

    joue.tree.setCurrentIndex(_index(joue, "suite", "apdu"))

    # C'est l'etat AFFICHE qu'on verifie, pas le contenu du tampon : le
    # panneau bascule sur son etat vide et l'editeur passe derriere. Le texte
    # qu'il garde en memoire n'est vu par personne, et son fichier est oublie
    # -- donc rien ne sera reecrit sur disque.
    assert joue.results.source.stack.currentWidget() is joue.results.source.empty
    assert joue.results.source.path() is None
    assert joue.results.logs.views[0].text() == ""


# ------------------------------------------------------- la ligne Campaign

@pytest.fixture
def avec_campagne(avec_source, tmp_path):
    """Une campagne qui couvre `test_atr` et `test_aid[A1]` -- deux feuilles
    dont l'ancetre commun est `test_select.py`, pas `suite` ni `apdu`. Assise
    sur `avec_source` : le fichier existe reellement, pour verifier que la
    campagne prend le pas sur SA source normale sans que le test ne prouve
    rien faute de fichier a montrer.

    Le fichier de campagne n'est pas range sous un dossier nomme comme l'un
    des ancetres de l'arbre : `_rebuild_campaign_roots` retomberait alors sur
    ce nom-la plutot que sur l'ancetre commun des tests couverts, ce que ce
    test doit justement verifier.
    """
    from runner.domain import campaign as campaign_mod

    fenetre = avec_source
    campagne_path = tmp_path / "campaign.yaml"
    campagne_path.write_text(
        """\
name: ATR configurations
campaign:
  - name: Configuration A
    config: setup_a.py
    tests:
      - suite/apdu/test_select.py::test_atr
  - name: Configuration B
    config: setup_b.py
    tests:
      - suite/apdu/test_select.py::test_aid[A1]
""",
        encoding="utf-8",
    )
    couverts = (NODEIDS[0], NODEIDS[1])
    campagnes = campaign_mod.discover_campaigns(str(tmp_path), couverts)
    assert campagnes, "la campagne de test n'a pas ete detectee"

    fenetre._campaigns = campagnes
    fenetre.model.set_campaigns(campaign_mod.memberships(campagnes))
    return fenetre


def test_clicking_the_campaign_row_shows_its_configurations_in_detail(avec_campagne):
    avec_campagne.tree.setCurrentIndex(
        _index(avec_campagne, "suite", "apdu", "test_select.py"))

    fiche = _fiche(avec_campagne)
    # `isVisible()` reflete la fenetre entiere, jamais montree dans ce test :
    # c'est l'intention -- posee par `setVisible()` dans `_remplir_campagne`
    # -- qu'on verifie, via ce que la ligne contient reellement.
    assert not fiche.campaign_host.isHidden()
    assert fiche.campaign_title.text() == "Campaign · 2 configurations"
    assert fiche._campaign_cards.count() == 2


def test_the_campaign_card_names_its_setup_and_test_count(avec_campagne):
    avec_campagne.tree.setCurrentIndex(
        _index(avec_campagne, "suite", "apdu", "test_select.py"))

    fiche = _fiche(avec_campagne)
    premiere = fiche._campaign_cards.itemAt(0).widget()
    assert "Configuration A" in premiere.findChild(QLabel).text()
    textes = " ".join(label.text() for label in premiere.findChildren(QLabel))
    assert "setup_a.py" in textes
    assert "1 test" in textes


def test_clicking_the_campaign_row_shows_its_yaml_in_source(avec_campagne):
    avec_campagne.tree.setCurrentIndex(
        _index(avec_campagne, "suite", "apdu", "test_select.py"))

    assert _source_chargee(avec_campagne)
    texte = avec_campagne.results.source.editor.toPlainText()
    assert "ATR configurations" in texte
    assert avec_campagne.results.source.path().name == "campaign.yaml"


def test_a_row_that_does_not_carry_the_campaign_shows_neither(avec_campagne):
    """`test_aid[A1]` est couvert par la campagne, mais ce n'est pas LUI qui
    porte le badge -- son ancetre commun avec `test_atr` le porte. Cliquer ce
    descendant ne doit donc pas montrer les cartes de configuration : elles
    parleraient d'une campagne plus large que ce que la ligne represente."""
    avec_campagne.tree.setCurrentIndex(
        _index(avec_campagne, "suite", "apdu", "test_select.py", "test_aid"))

    fiche = _fiche(avec_campagne)
    assert fiche.campaign_host.isHidden()
    assert fiche._campaign_cards.count() == 0
    assert avec_campagne.results.source.path().name == "test_select.py"


def test_the_campaign_row_hides_the_generic_summary(avec_campagne):
    """Les rubans et la liste d'echecs fondent plusieurs executions du meme
    test en un seul statut -- exactement ce que la vue Campaign detaille. Les
    montrer ensemble contredirait l'une ou l'autre."""
    avec_campagne.tree.setCurrentIndex(
        _index(avec_campagne, "suite", "apdu", "test_select.py"))
    fiche = _fiche(avec_campagne)
    assert fiche.ribbons_host.isHidden()
    assert fiche.failures.isHidden()
    assert not fiche.campaign_results_view.isHidden()

    avec_campagne.tree.setCurrentIndex(_index(avec_campagne, "suite", "apdu"))
    assert not fiche.ribbons_host.isHidden()
    assert not fiche.failures.isHidden()
    assert fiche.campaign_results_view.isHidden()


# ------------------------------------------- le resultat de chaque execution

@pytest.fixture
def avec_campagne_le_meme_test_partout(avec_source, tmp_path):
    """`test_atr` couvert par LES DEUX configurations -- le cas qui motive la
    fonctionnalite : un meme test, deux verdicts possibles, qu'aucune vue ne
    doit fondre en un seul."""
    from runner.domain import campaign as campaign_mod

    fenetre = avec_source
    (tmp_path / "campaign.yaml").write_text(
        """\
name: ATR configurations
campaign:
  - name: Configuration A
    config: setup_a.py
    tests:
      - suite/apdu/test_select.py::test_atr
  - name: Configuration B
    config: setup_b.py
    tests:
      - suite/apdu/test_select.py::test_atr
""",
        encoding="utf-8",
    )
    campagnes = campaign_mod.discover_campaigns(str(tmp_path), (NODEIDS[0],))
    assert campagnes, "la campagne de test n'a pas ete detectee"

    fenetre._campaigns = campagnes
    fenetre.model.set_campaigns(campaign_mod.memberships(campagnes))
    fenetre._campagne = campagnes[0]
    return fenetre


def _jouer_campagne(fenetre, campagne, par_scenario: dict, lecteur=None):
    """Simule un run termine : un `PhaseReport` par scenario, comme
    `execution.py` les construit vraiment."""
    from runner.domain.models import PhaseReport, Reader, ReaderReport

    lecteur = lecteur or Reader("", 0)
    phases = [
        PhaseReport(f"0:{position}", scenario.name, campagne.name,
                    statuses=par_scenario.get(scenario.name, {}))
        for position, scenario in enumerate(campagne.scenarios)
    ]
    fenetre.results.set_readers((lecteur,))
    fenetre.results.set_report(ReaderReport(reader=lecteur, phases=phases))


def test_the_same_test_can_disagree_across_configurations(
    avec_campagne_le_meme_test_partout,
):
    """Le coeur de la demande : `test_atr` passe en A, echoue en B -- les deux
    doivent rester lisibles separement, dans la liste comme dans la matrice."""
    fenetre = avec_campagne_le_meme_test_partout
    campagne = fenetre._campagne
    _jouer_campagne(fenetre, campagne, {
        "Configuration A": {NODEIDS[0]: Status.PASSED},
        "Configuration B": {NODEIDS[0]: Status.FAILED},
    })

    resultats = fenetre.results.campaign_results(campagne)
    assert resultats["Configuration A"][NODEIDS[0]] == {0: Status.PASSED}
    assert resultats["Configuration B"][NODEIDS[0]] == {0: Status.FAILED}

    fenetre.tree.setCurrentIndex(
        _index(fenetre, "suite", "apdu", "test_select.py"))
    vue = _fiche(fenetre).campaign_results_view

    config_a = vue.tree.topLevelItem(0)
    config_b = vue.tree.topLevelItem(1)
    assert config_a.child(0).text(1) == "PASSED"
    assert config_b.child(0).text(1) == "FAILED"

    vue.matrix_button.click()
    assert vue.table.item(0, 0).text() == "PASSED"
    assert vue.table.item(0, 1).text() == "FAILED"


def test_the_matrix_rows_are_not_shuffled(avec_campagne):
    """Chaque ligne doit rester CELLE du test qu'elle nomme : melangees, la
    case d'un test dans sa PROPRE configuration se retrouverait vide plutot
    que d'afficher son resultat."""
    from runner.domain.models import PhaseReport, ReaderReport
    from runner.ui.campaign_results import _libelle_test

    fenetre = avec_campagne
    campagne = fenetre._campaigns[0]
    fenetre.results.set_readers((Reader("", 0),))
    fenetre.results.set_report(ReaderReport(reader=Reader("", 0), phases=[
        PhaseReport("0:0", "Configuration A", campagne.name,
                    statuses={NODEIDS[0]: Status.PASSED}),
        PhaseReport("0:1", "Configuration B", campagne.name,
                    statuses={NODEIDS[1]: Status.FAILED}),
    ]))

    fenetre.tree.setCurrentIndex(
        _index(fenetre, "suite", "apdu", "test_select.py"))
    vue = _fiche(fenetre).campaign_results_view
    vue.matrix_button.click()

    def _ligne(etiquette):
        for r in range(vue.table.rowCount()):
            if vue.table.verticalHeaderItem(r).text() == etiquette:
                return r
        raise AssertionError(f"{etiquette} introuvable")

    # Chaque test n'est couvert que par SA propre configuration : la case
    # correspondante doit porter son resultat, jamais vide.
    assert vue.table.item(_ligne(_libelle_test(NODEIDS[0])), 0).text() == "PASSED"
    assert vue.table.item(_ligne(_libelle_test(NODEIDS[1])), 1).text() == "FAILED"


def test_a_test_not_yet_run_says_so_instead_of_a_status(
    avec_campagne_le_meme_test_partout,
):
    fenetre = avec_campagne_le_meme_test_partout
    campagne = fenetre._campagne
    _jouer_campagne(fenetre, campagne, {"Configuration A": {NODEIDS[0]: Status.PASSED}})

    fenetre.tree.setCurrentIndex(
        _index(fenetre, "suite", "apdu", "test_select.py"))
    vue = _fiche(fenetre).campaign_results_view

    assert vue.tree.topLevelItem(1).child(0).text(1) == "not run"
    vue.matrix_button.click()
    assert vue.table.item(0, 1).text() == "not run"


def test_a_running_phase_shows_its_results_before_the_reader_finishes(
    avec_campagne_le_meme_test_partout,
):
    """`_phase_reports` ne se remplit qu'a la toute fin du lecteur : pendant
    le run, seuls les evenements en direct existent. Sans eux, cliquer la
    ligne Campaign en cours de run montrerait tout vide."""
    from runner.domain.models import Outcome

    fenetre = avec_campagne_le_meme_test_partout
    campagne = fenetre._campagne
    fenetre.results.set_readers((Reader("", 0),))

    fenetre.results.update_statuses(NODEIDS[0], {}, outcome=Outcome(
        NODEIDS[0], Status.PASSED, 0, campagne.name, "0:0", "Configuration A"))

    resultats = fenetre.results.campaign_results(campagne)
    assert resultats["Configuration A"][NODEIDS[0]] == {0: Status.PASSED}
    assert resultats["Configuration B"] == {}


def test_a_finished_report_is_not_overwritten_by_a_live_leftover(
    avec_campagne_le_meme_test_partout,
):
    """Un residu en direct d'un ANCIEN clic ne doit jamais ecraser le verdict
    definitif d'une phase deja terminee."""
    from runner.domain.models import Outcome

    fenetre = avec_campagne_le_meme_test_partout
    campagne = fenetre._campagne
    _jouer_campagne(fenetre, campagne, {
        "Configuration A": {NODEIDS[0]: Status.PASSED},
    })
    # Un residu en direct, perime, pretend le contraire.
    fenetre.results.update_statuses(NODEIDS[0], {}, outcome=Outcome(
        NODEIDS[0], Status.FAILED, 0, campagne.name, "0:0", "Configuration A"))

    resultats = fenetre.results.campaign_results(campagne)
    assert resultats["Configuration A"][NODEIDS[0]] == {0: Status.PASSED}


# ---------------------------------------------------------------- la barre

def test_the_ribbon_paints_every_status_it_is_given(qapp):
    from runner.ui.widgets import StatusRibbon

    ruban = StatusRibbon()
    ruban.resize(200, 8)
    ruban.set_counts({Status.PASSED: 3, Status.FAILED: 1})
    image = ruban.grab().toImage()

    vus = {image.pixelColor(x, 4).name()
           for x in range(2, image.width() - 2)}
    from runner.ui import tokens as t

    assert t.status_color(Status.PASSED) in vus
    assert t.status_color(Status.FAILED) in vus


def test_the_ribbon_is_proportional(qapp):
    """C'est tout son interet : la proportion se voit sans lire les nombres."""
    from runner.ui import tokens as t
    from runner.ui.widgets import StatusRibbon

    ruban = StatusRibbon()
    ruban.resize(200, 8)
    ruban.set_counts({Status.PASSED: 3, Status.FAILED: 1})
    image = ruban.grab().toImage()

    verts = sum(1 for x in range(image.width())
                if image.pixelColor(x, 4).name() == t.status_color(Status.PASSED))
    rouges = sum(1 for x in range(image.width())
                 if image.pixelColor(x, 4).name() == t.status_color(Status.FAILED))
    assert verts > 2 * rouges, f"{verts} verts pour {rouges} rouges"


def test_a_ribbon_with_nothing_still_draws_its_track(qapp):
    """Un lot entierement en attente ne dessinerait rien et se lirait comme un
    widget casse."""
    from runner.ui import tokens as t
    from runner.ui.widgets import StatusRibbon

    ruban = StatusRibbon()
    ruban.resize(200, 8)
    ruban.set_counts({})
    image = ruban.grab().toImage()

    assert image.pixelColor(100, 4).name() == t.BG_RAISED


def test_the_ribbon_says_the_numbers_on_hover(qapp):
    from runner.ui.widgets import StatusRibbon

    ruban = StatusRibbon()
    ruban.set_counts({Status.PASSED: 3, Status.FAILED: 1})
    assert "3 passed" in ruban.toolTip() and "1 failed" in ruban.toolTip()


# ------------------------------------------------------------------ theme

def test_the_group_card_follows_a_change_of_theme(joue, qapp):
    """Ses couleurs sont ecrites a la construction, comme celles de la fiche
    de test : sans rejeu, le rouge du theme sombre reste sur fond blanc."""
    from runner.ui import tokens as t

    joue.tree.setCurrentIndex(_index(joue, "suite"))
    joue.apply_theme("dark")
    fiche = _fiche(joue)
    sombre = fiche.failures.item(0).foreground().color().name()

    joue.apply_theme("light")
    clair = fiche.failures.item(0).foreground().color().name()

    assert sombre == t.DARK["STATUS_COLORS"][Status.FAILED]
    assert clair == t.LIGHT["STATUS_COLORS"][Status.FAILED]


# --------------------------------------------------- la source d'un regroupement

@pytest.fixture
def avec_source(joue, tmp_path):
    """Le fichier de test existe reellement : sans lui, rien a ouvrir."""
    fichier = tmp_path / "suite" / "apdu" / "test_select.py"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(
        "import pytest\n\n\n"
        "def test_atr():\n"
        "    assert True\n\n\n"
        "@pytest.mark.parametrize('aid', ['A1', 'A2'])\n"
        "def test_aid(aid):\n"
        "    assert aid\n",
        encoding="utf-8")
    return joue


def _source_chargee(fenetre) -> bool:
    panneau = fenetre.results.source
    return panneau.stack.currentWidget() is not panneau.empty


def test_clicking_a_py_file_shows_its_source(avec_source):
    """Le geste le plus courant apres avoir repere un fichier rouge."""
    avec_source.tree.setCurrentIndex(
        _index(avec_source, "suite", "apdu", "test_select.py"))

    assert _source_chargee(avec_source)
    assert "def test_atr" in avec_source.results.source.editor.toPlainText()


def test_a_module_opens_at_the_top(avec_source):
    """Sauter au premier test venu ferait manquer les imports et les fixtures
    qui le precedent -- souvent la raison de l'echec."""
    avec_source.tree.setCurrentIndex(
        _index(avec_source, "suite", "apdu", "test_select.py"))

    assert avec_source.results.source.editor.textCursor().blockNumber() == 0


def test_clicking_a_function_jumps_to_its_definition(avec_source):
    """Un test parametre est un regroupement, mais il porte un nom de
    fonction : cliquer dessus doit y emmener, comme sur une feuille."""
    avec_source.tree.setCurrentIndex(
        _index(avec_source, "suite", "apdu", "test_select.py", "test_aid"))

    texte = avec_source.results.source.editor.toPlainText()
    attendue = texte.splitlines().index("def test_aid(aid):")
    assert avec_source.results.source.editor.textCursor().blockNumber() == attendue


def test_a_folder_has_no_source_to_show(avec_source):
    """Garder celle du test precedent ferait croire qu'elle parle du dossier."""
    avec_source.tree.setCurrentIndex(
        _index(avec_source, "suite", "apdu", "test_select.py"))
    assert _source_chargee(avec_source)

    avec_source.tree.setCurrentIndex(_index(avec_source, "suite", "apdu"))
    assert not _source_chargee(avec_source)


def test_a_group_never_shows_the_logs_of_a_test(avec_source, tmp_path):
    """Les logs sont ecrits PAR TEST : aucun ne repond pour un lot entier.

    Un log est reellement pose sur le disque et charge : sans lui la vue etait
    deja vide et le test ne prouvait rien.
    """
    journal = (tmp_path / "logs" / "20260818"
               / "Cosmo11Secured Reader" / "suite" / "apdu")
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "test_atr.log").write_text("APDU >> 00A4\n", encoding="utf-8")
    avec_source.results.set_log_root(tmp_path / "logs")

    avec_source.tree.setCurrentIndex(avec_source.model.index_for_nodeid(NODEIDS[0]))
    assert "APDU" in avec_source.results.logs.views[0].text(), (
        "le log n'a pas ete charge : il n'y aurait rien a effacer")

    avec_source.tree.setCurrentIndex(
        _index(avec_source, "suite", "apdu", "test_select.py"))
    assert avec_source.results.logs.views[0].text() == ""
