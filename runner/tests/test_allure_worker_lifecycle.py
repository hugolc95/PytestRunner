"""Regression tests for the Allure worker lifecycle."""

from __future__ import annotations

import subprocess

from runner.services.allure_service import AllureReportWorker


def test_done_is_emitted_only_after_the_qthread_has_finished(qapp, monkeypatch, tmp_path):
    """Dropping the worker from the ``done`` slot must never kill a live QThread."""
    monkeypatch.setattr(
        "runner.services.allure_service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )

    resultats = tmp_path / "results"
    resultats.mkdir()
    rapport = tmp_path / "report"
    worker = AllureReportWorker("allure", resultats, rapport, {})

    observed = []
    worker.done.connect(
        lambda ok, detail: observed.append((ok, detail, worker.isFinished())))

    worker.start()
    assert worker.wait(3000)

    for _ in range(20):
        qapp.processEvents()
        if observed:
            break

    assert observed == [(True, "", True)]
