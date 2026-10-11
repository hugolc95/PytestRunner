"""Run copies must reach tests that open the workspace YAML directly."""
import sys
import os

from runner.domain.execution import ReaderRun, collect
from runner.domain.models import Reader, RunRequest, Status
from runner.domain.reader_isolation import ENV_CONFIG, ENV_CONFIG_SOURCE


def test_private_configuration_is_used_for_collection_and_execution(tmp_path):
    source = tmp_path / "config.yaml"
    source.write_text("1", encoding="utf-8")
    private = tmp_path / "run-copy.yaml"
    private.write_text("2", encoding="utf-8")
    (tmp_path / "test_private.py").write_text(
        "from pathlib import Path\nimport pytest\n"
        "@pytest.mark.parametrize('step', range(int(Path('config.yaml').read_text())))\n"
        "def test_private(step):\n"
        "    with open('config.yaml', encoding='utf-8') as stream:\n"
        "        assert stream.read() == '2'\n", encoding="utf-8")
    env = {**os.environ, ENV_CONFIG: str(private), ENV_CONFIG_SOURCE: str(source)}
    collection = collect(str(tmp_path), sys.executable, env)
    assert len(collection.nodeids) == 2
    request = RunRequest(workspace=str(tmp_path), interpreter=sys.executable,
                         nodeids=collection.nodeids, readers=(), config_path=str(private))
    report = ReaderRun(request, Reader("", 0), env).run(lambda *_: None, lambda *_: None)
    assert report.exit_code == 0, report.output
    assert report.counts.get(Status.PASSED) == 2
    assert source.read_text(encoding="utf-8") == "1"
