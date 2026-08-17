"""Choisir les lecteurs a parcourir, et les enchainer ou les mener de front.

Un workspace peut declarer plusieurs lecteurs. Les tester tous est le cas
courant, mais pas toujours ce qu'on veut : un lecteur debranche, une campagne
qu'on refait sur un seul. C'est ce que l'ancienne interface permettait avec
ses cases a cocher, et que la refonte avait perdu.

Le mode d'enchainement vient du workspace, pas de l'interface : c'est une
contrainte du materiel ou du code de test, pas une preference.
"""

from __future__ import annotations

import time

import pytest

from runner.domain.models import Reader, ReaderReport, RunRequest, Status
from runner.domain.tree import build_tree
from runner.domain.workspace import MODE_PARALLELE, MODE_SEQUENTIEL, Workspace

NODEIDS = [
    "suite/apdu/test_select.py::test_atr",
    "suite/apdu/test_select.py::test_aid",
]


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _workspace(tmp_path, texte: str) -> Workspace:
    (tmp_path / "config.yml").write_text(texte, encoding="utf-8")
    return Workspace.load(str(tmp_path))


# ---------------------------------------------------------------------------
# Le mode, lu dans la configuration du workspace
# ---------------------------------------------------------------------------

def test_readers_run_together_unless_the_workspace_says_otherwise(tmp_path):
    """Parallele par defaut : rien a declarer pour obtenir le mode rapide.

    Le fichier de configuration n'est plus un point de contention -- chaque
    processus en lit une copie ou sa cle `Reader` est deja posee.
    """
    espace = _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n")
    assert espace.reader_mode == MODE_PARALLELE


@pytest.mark.parametrize("ligne", [
    "reader_mode: sequential",
    "reader_mode: SEQUENTIAL",
    "reader_mode:   sequential  ",
    "readers_mode: sequential",
    "mode_lecteur: sequential",
    "reader-mode: sequential",
])
def test_the_sequential_mode_is_recognised_however_it_is_written(tmp_path, ligne):
    """Une meme notion porte des noms differents d'un projet a l'autre, et une
    valeur tapee a la main porte souvent une majuscule ou une espace."""
    espace = _workspace(tmp_path, f"Reader: A\n{ligne}\n")
    assert espace.reader_mode == MODE_SEQUENTIEL


def test_an_unknown_mode_falls_back_to_running_them_together(tmp_path):
    """Une faute de frappe ne doit pas immobiliser une campagne : le mode
    inconnu est ignore, pas obei a moitie."""
    espace = _workspace(tmp_path, "Reader: A\nreader_mode: paralell\n")
    assert espace.reader_mode == MODE_PARALLELE


def test_the_mode_is_found_inside_a_section(tmp_path):
    espace = _workspace(tmp_path, "Reader: A\nrun:\n  reader_mode: sequential\n")
    assert espace.reader_mode == MODE_SEQUENTIEL


# ---------------------------------------------------------------------------
# Ce que la requete transporte
# ---------------------------------------------------------------------------

def test_a_request_runs_them_together_unless_told(tmp_path):
    requete = RunRequest("/w", "python", tuple(NODEIDS), (Reader("A", 0),))
    assert requete.sequential is False


def test_the_total_counts_only_the_readers_the_run_will_visit():
    """Le compteur « restants » et la barre d'avancement en dependent : compter
    les lecteurs declares plutot que ceux retenus laisserait la barre bloquee
    a mi-course."""
    requete = RunRequest("/w", "python", tuple(NODEIDS), (Reader("B", 1),))
    assert requete.total_tests == 2


# ---------------------------------------------------------------------------
# L'enchainement, dans le service
# ---------------------------------------------------------------------------

class _FauxRun:
    """Un run qui ne lance pas pytest, mais occupe son fil un vrai moment.

    Le fil et ses signaux sont conserves : c'est la, et pas dans le domaine,
    que vivent les defauts d'enchainement qu'on cherche.
    """

    journal: list = []
    duree = 0.15
    # Le dernier lecteur finit le PREMIER. Sans cela les rapports revenaient
    # deja dans l'ordre des colonnes par accident, et le tri du service
    # n'aurait rien eu a corriger.
    durees: dict = {}

    def __init__(self, request, reader, env):
        self._reader = reader
        self._annule = False

    def cancel(self) -> None:
        self._annule = True

    def run(self, on_line, on_outcome):
        debut = time.monotonic()
        _FauxRun.journal.append(("debut", self._reader.index, debut))
        duree = self.durees.get(self._reader.index, self.duree)
        while time.monotonic() - debut < duree and not self._annule:
            time.sleep(0.005)
        on_line(f"reader {self._reader.index} done")
        _FauxRun.journal.append(("fin", self._reader.index, time.monotonic()))
        return ReaderReport(reader=self._reader, cancelled=self._annule)


@pytest.fixture
def faux_runs(monkeypatch):
    from runner.domain import execution

    _FauxRun.journal = []
    _FauxRun.durees = {}
    monkeypatch.setattr(execution, "ReaderRun", _FauxRun)
    return _FauxRun


def _intervalles() -> dict:
    """Debut et fin de chaque lecteur, releves dans le fil de ce lecteur."""
    par_lecteur: dict = {}
    for quoi, index, instant in _FauxRun.journal:
        creneau = par_lecteur.setdefault(index, [None, None])
        creneau[0 if quoi == "debut" else 1] = instant
    return par_lecteur


def _attendre(qapp, condition, limite=10.0) -> bool:
    debut = time.monotonic()
    while time.monotonic() - debut < limite:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def _service(qapp):
    from runner.services.run_service import RunService

    return RunService()


def _requete(sequential: bool) -> RunRequest:
    return RunRequest("/w", "python", tuple(NODEIDS),
                      (Reader("A", 0), Reader("B", 1)), sequential=sequential)


def test_in_parallel_mode_both_readers_are_under_way_at_once(qapp, faux_runs):
    service = _service(qapp)
    service.start(_requete(sequential=False), {})
    assert _attendre(qapp, lambda: not service.busy), "le run n'a jamais fini"
    service.wait()

    creneaux = _intervalles()
    assert set(creneaux) == {0, 1}
    premier, second = sorted(creneaux.values(), key=lambda c: c[0])
    assert second[0] < premier[1], (
        "les deux lecteurs ne se sont pas recouverts : ils se sont enchaines")


def test_in_sequential_mode_the_second_reader_waits_for_the_first(qapp, faux_runs):
    """Le mode existe pour ce que l'isolation ne peut pas separer : du materiel
    qui ne supporte pas deux campagnes, un log unique. Se recouvrir ne serait
    pas une lenteur, ce serait la panne qu'on cherche a eviter."""
    service = _service(qapp)
    service.start(_requete(sequential=True), {})
    assert _attendre(qapp, lambda: not service.busy), "le run n'a jamais fini"
    service.wait()

    creneaux = _intervalles()
    assert set(creneaux) == {0, 1}
    premier, second = sorted(creneaux.values(), key=lambda c: c[0])
    assert second[0] >= premier[1], (
        "le deuxieme lecteur a demarre avant la fin du premier")


def test_the_run_never_looks_idle_between_two_sequential_readers(qapp, faux_runs):
    """`busy` retombant a faux au milieu du run rallumerait le bouton Run, et
    une deuxieme campagne partirait par-dessus la premiere.

    Le trou est etroit : le premier fil est fini, le second pas encore parti.
    L'echantillonner depuis la boucle d'evenements ne le trouvait pas -- le
    `processEvents` qui precede chaque mesure demarre justement le suivant. On
    se place donc DANS le creux : `reader_finished` est emis avant que le
    service ne prenne le lecteur en file.
    """
    service = _service(qapp)
    releves = []
    service.reader_finished.connect(lambda _r: releves.append(service.busy))

    service.start(_requete(sequential=True), {})
    assert _attendre(qapp, lambda: len(releves) == 2), "le run n'a jamais fini"
    service.wait()

    # Le premier releve est pris alors qu'il reste un lecteur a jouer ; le
    # second a la toute fin, ou le service a le droit d'etre libre.
    assert releves[0] is True, (
        "le service s'est declare libre alors qu'un lecteur restait a jouer")


def test_stopping_a_sequential_run_does_not_start_the_next_reader(qapp, faux_runs):
    service = _service(qapp)
    service.start(_requete(sequential=True), {})
    assert _attendre(qapp, lambda: _FauxRun.journal), "le premier n'a pas demarre"

    service.cancel()
    assert _attendre(qapp, lambda: not service.busy), "l'arret n'a pas abouti"
    service.wait()
    qapp.processEvents()

    assert set(_intervalles()) == {0}, (
        "un lecteur de la file est parti malgre l'arret")


def test_a_stopped_sequential_run_still_reports_that_it_is_over(qapp, faux_runs):
    """Les lecteurs restes en file ne rendront jamais de rapport.

    Compares au nombre de lecteurs PREVUS, ils empechaient `finished` d'etre
    emis : la fenetre restait en « run en cours », bouton Run eteint et Stop
    allume, jusqu'a la fermeture.
    """
    service = _service(qapp)
    bilans = []
    service.finished.connect(bilans.append)

    service.start(_requete(sequential=True), {})
    assert _attendre(qapp, lambda: _FauxRun.journal), "le premier n'a pas demarre"
    service.cancel()

    assert _attendre(qapp, lambda: bilans), (
        "aucun bilan de fin apres l'arret : l'interface resterait bloquee")
    service.wait()
    assert len(bilans[0]) == 1, "seul le lecteur demarre doit rendre un rapport"


def test_the_reports_come_back_in_column_order(qapp, faux_runs):
    """Ils arrivent dans l'ordre ou les lecteurs finissent ; un bilan qui change
    de disposition d'un run a l'autre se relit mal."""
    faux_runs.durees = {0: 0.30, 1: 0.05}   # le deuxieme lecteur finit d'abord

    service = _service(qapp)
    rendus, bilans = [], []
    service.reader_finished.connect(lambda r: rendus.append(r.reader.index))
    service.finished.connect(bilans.append)

    service.start(_requete(sequential=False), {})
    assert _attendre(qapp, lambda: bilans), "le run n'a jamais fini"
    service.wait()

    assert rendus == [1, 0], (
        "les lecteurs n'ont pas fini dans le desordre : le tri ne serait pas "
        "sollicite et le test ne prouverait rien")
    assert [r.reader.index for r in bilans[0]] == [0, 1]


# ---------------------------------------------------------------------------
# La barre de lecteurs, dans la fenetre
# ---------------------------------------------------------------------------

@pytest.fixture
def fenetre(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from runner.ui.main_window import APP, ORG, MainWindow

    QSettings(ORG, APP).clear()
    f = MainWindow()
    yield f
    f.settings.clear()


def _charger(fenetre, espace: Workspace) -> None:
    """Charge un workspace par le VRAI chemin, sans lancer de collecte.

    Rejouer ici ce que fait `_on_collected` ferait un test qui se verifie
    lui-meme : il continuerait de passer alors que la fenetre, elle, cablerait
    tout autrement.
    """
    from runner.domain.execution import Collection

    fenetre.workspace = espace
    fenetre._on_collected(Collection(nodeids=tuple(NODEIDS)))


@pytest.mark.parametrize("config, visible", [
    ("Reader: A\n", False),
    ("", False),
    ("Reader: A\nReaders:\n  - B\n", True),
])
def test_the_bar_appears_only_when_there_is_a_choice_to_make(fenetre, tmp_path,
                                                             config, visible):
    """Un seul lecteur ne se choisit pas : une case a cocher unique, toujours
    cochee, n'est qu'un element de plus a comprendre."""
    _charger(fenetre, _workspace(tmp_path, config))
    assert fenetre.readers_bar.isHidden() is (not visible)


def test_every_reader_is_included_to_begin_with(fenetre, tmp_path):
    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n  - C\n"))
    assert fenetre.readers_bar.selected_indexes() == (0, 1, 2)
    assert len(fenetre._readers_to_run()) == 3


def test_unchecking_a_reader_keeps_the_others_on_their_own_column(fenetre, tmp_path):
    """Leur `index` doit survivre au filtrage.

    Renumeroter les lecteurs restants ferait atterrir les verdicts du deuxieme
    dans la colonne du premier des qu'on en decoche un -- un resultat juste,
    affiche en face du mauvais lecteur.
    """
    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n  - C\n"))
    fenetre.readers_bar._toggles[0].setChecked(False)

    retenus = fenetre._readers_to_run()
    assert [l.index for l in retenus] == [1, 2]
    assert [l.name for l in retenus] == ["B", "C"]


def test_unchecking_a_reader_does_not_hide_what_it_already_showed(fenetre, tmp_path):
    """Les colonnes suivent les lecteurs DECLARES, pas les lecteurs coches :
    en faire disparaitre une effacerait de l'ecran les resultats du run
    precedent."""
    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n"))
    fenetre.model.apply_outcome(NODEIDS[0], Status.FAILED, 1)
    colonnes = fenetre.model.columnCount()

    fenetre.readers_bar._toggles[1].setChecked(False)

    assert fenetre.model.columnCount() == colonnes
    assert fenetre.model.statuses_for_nodeid(NODEIDS[0])[1] is Status.FAILED


def test_with_no_reader_ticked_there_is_nothing_to_run(fenetre, tmp_path):
    """Le bouton s'eteint plutot que de repondre par une boite de dialogue : la
    cause est a l'ecran, juste au-dessus de lui."""
    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n"))
    fenetre.model.set_all_checked(True)
    fenetre._update_actions()
    assert fenetre.run_button.isEnabled()

    for bouton in fenetre.readers_bar._toggles:
        bouton.setChecked(False)

    assert fenetre._readers_to_run() == ()
    assert not fenetre.run_button.isEnabled()
    assert not fenetre.act_run.isEnabled()


def test_a_workspace_without_readers_can_still_run(fenetre, tmp_path):
    """Sans lecteur declare, il n'y a rien a cocher -- et surtout rien qui
    doive eteindre le bouton Run."""
    _charger(fenetre, _workspace(tmp_path, "LOG_PATH: logs\n"))
    fenetre.model.set_all_checked(True)
    fenetre._update_actions()

    assert fenetre.workspace.readers == ()
    assert fenetre.run_button.isEnabled()


def test_the_window_says_which_readers_the_next_run_will_visit(fenetre, tmp_path):
    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n"))
    fenetre.readers_bar._toggles[1].setChecked(False)
    assert "A" in fenetre.status_label.text()
    assert "B" not in fenetre.status_label.text()


def test_the_sequential_mode_is_shown_because_it_explains_the_wait(fenetre,
                                                                   tmp_path):
    """Deux lecteurs l'un apres l'autre prennent deux fois plus longtemps ;
    sans indication, le run parait simplement lent."""
    _charger(fenetre, _workspace(
        tmp_path, "Reader: A\nReaders:\n  - B\nreader_mode: sequential\n"))
    assert not fenetre.readers_bar._mode.isHidden()
    assert fenetre.readers_bar._mode.text()

    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n"))
    assert fenetre.readers_bar._mode.isHidden()


def test_the_toggles_follow_a_change_of_theme(fenetre, tmp_path):
    """Leur teinte vient du lecteur, pas de la feuille globale.

    Le balayage de `_restyle` les atteint directement -- c'est pour cela que la
    barre n'a pas de `restyle()` a elle. Si ce balayage cessait de descendre
    jusqu'aux boutons, ils garderaient les couleurs de l'ancien theme.
    """
    from runner.ui import tokens as t

    _charger(fenetre, _workspace(tmp_path, "Reader: A\nReaders:\n  - B\n"))
    fenetre.apply_theme("dark")
    sombre = fenetre.readers_bar._toggles[0].styleSheet()
    fenetre.apply_theme("light")
    clair = fenetre.readers_bar._toggles[0].styleSheet()

    assert t.DARK["READER_COLORS"][0] in sombre
    assert t.LIGHT["READER_COLORS"][0] in clair


def test_an_excluded_reader_stays_out_of_the_request(fenetre, tmp_path,
                                                     monkeypatch):
    """Le bout qui compte vraiment : ce que la fenetre demande au service."""
    _charger(fenetre, _workspace(
        tmp_path, "Reader: A\nReaders:\n  - B\nreader_mode: sequential\n"))
    fenetre.model.set_all_checked(True)
    fenetre.readers_bar._toggles[0].setChecked(False)

    monkeypatch.setattr(fenetre, "_require_interpreter", lambda: "python")
    demandes = []
    monkeypatch.setattr(fenetre.service, "start",
                        lambda requete, env: demandes.append(requete) or True)

    fenetre.run_selected()

    assert len(demandes) == 1
    requete = demandes[0]
    assert [l.name for l in requete.readers] == ["B"]
    assert requete.sequential is True
    assert requete.total_tests == len(requete.nodeids)
