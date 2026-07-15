from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import shlex



@dataclass
class CampaignTest:
    nodeid: str
    repeat: int = 1
    name: str | None = None


@dataclass
class CampaignScenario:
    name: str
    setup: str | list[str] | None = None
    tests: list[CampaignTest] = field(default_factory=list)


@dataclass
class Campaign:
    name: str
    workspace: str
    scenarios: list[CampaignScenario] = field(default_factory=list)
    campaign_file: str | None = None
    pythonpath: list[str] = field(default_factory=list)


def _load_yaml(path: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "PyYAML is required to read campaign.yml. Install it with: pip install pyyaml"
        ) from exc

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("campaign.yml must contain a YAML object at root.")

    return data


def _as_command(value: Any) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return [str(x) for x in value]
    raise ValueError(f"Invalid setup command: {value!r}")


def _as_pythonpath(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value]
    raise ValueError("pythonpath must be a string or a list of strings.")


def _as_test(value: Any) -> CampaignTest:
    if isinstance(value, str):
        return CampaignTest(nodeid=value.strip(), repeat=1, name=None)

    if isinstance(value, dict):
        nodeid = value.get("nodeid") or value.get("test") or value.get("path")
        if not nodeid:
            raise ValueError(f"Campaign test entry misses nodeid/test/path: {value!r}")
        repeat = int(value.get("repeat", 1))
        repeat = max(1, repeat)
        name = value.get("name")
        return CampaignTest(nodeid=str(nodeid).strip(), repeat=repeat, name=str(name) if name else None)

    raise ValueError(f"Invalid test entry: {value!r}")


def load_campaign(path: str) -> Campaign:
    campaign_path = Path(path).expanduser().resolve()
    data = _load_yaml(str(campaign_path))

    name = str(data.get("name") or campaign_path.stem)

    workspace = data.get("workspace") or data.get("root") or "."
    workspace_path = Path(str(workspace))
    if not workspace_path.is_absolute():
        workspace_path = (campaign_path.parent / workspace_path).resolve()

    raw_pythonpath = data.get("pythonpath") or data.get("python_path") or []
    pythonpath_entries: list[str] = []
    for entry in _as_pythonpath(raw_pythonpath):
        entry_path = Path(entry)
        if not entry_path.is_absolute():
            entry_path = (workspace_path / entry_path).resolve()
        pythonpath_entries.append(str(entry_path))

    # Always include the resolved workspace itself so imports like `from TSu...`
    # work when workspace points to the repository/test root. Additional entries
    # from campaign.yml can support legacy imports like `from conftest import ...`.
    workspace_str = str(workspace_path)
    if workspace_str not in pythonpath_entries:
        pythonpath_entries.insert(0, workspace_str)

    raw_scenarios = data.get("scenarios") or data.get("campaign") or []
    if not isinstance(raw_scenarios, list):
        raise ValueError("campaign.yml must contain a 'scenarios:' list.")

    scenarios: list[CampaignScenario] = []

    for index, raw in enumerate(raw_scenarios, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Scenario #{index} must be a YAML object.")

        scenario_name = str(raw.get("name") or f"Scenario {index}")
        setup = _as_command(raw.get("setup") or raw.get("config") or raw.get("script"))

        raw_tests = raw.get("tests") or []
        if not isinstance(raw_tests, list):
            raise ValueError(f"Scenario '{scenario_name}' must contain tests as a list.")

        tests = [_as_test(t) for t in raw_tests]
        scenarios.append(CampaignScenario(name=scenario_name, setup=setup, tests=tests))

    return Campaign(
        name=name,
        workspace=str(workspace_path),
        scenarios=scenarios,
        campaign_file=str(campaign_path),
        pythonpath=pythonpath_entries,
    )


def command_to_display(command: str | list[str] | None) -> str:
    if command is None:
        return ""
    if isinstance(command, list):
        return " ".join(shlex.quote(str(x)) for x in command)
    return command
