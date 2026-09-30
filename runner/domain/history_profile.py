"""Capture launch settings and turn an archived run into a portable profile."""

from dataclasses import asdict
from pathlib import Path

from runner.domain.execution_profile import (
    ExecutionOptions, ExecutionProfile, ProfileValidationError, ReportOptions,
    validate_profile, report_options_from_dict,
)


def capture_profile(request, profile=None, name="") -> dict | None:
    """Read the configuration at launch, never from the current workspace at export."""
    config_name, config_text = "", ""
    if request.config_path:
        try:
            path = Path(request.config_path)
            config_text = path.read_text(encoding="utf-8-sig")
            config_name = (profile.configuration_name if profile and
                           profile.configuration_name else path.name)
        except (OSError, UnicodeError):
            return None
    captured = ExecutionProfile(
        name=name or (profile.name if profile else "Recorded run"),
        sequence=list(profile.sequence if profile else request.nodeids),
        configuration_name=config_name, configuration_text=config_text,
        execution=profile.execution if profile else ExecutionOptions(),
        reports=profile.reports if profile else ReportOptions(),
    )
    return asdict(captured)


def profile_from_entry(entry, name="", configuration_path=None) -> ExecutionProfile:
    saved = entry.replay_profile
    try:
        if saved is not None:
            profile = ExecutionProfile(
                name=name or saved["name"], sequence=list(saved["sequence"]),
                configuration_name=saved["configuration_name"],
                configuration_text=saved["configuration_text"],
                execution=ExecutionOptions(**saved["execution"]),
                reports=report_options_from_dict(saved["reports"]),
            )
        else:
            sequence = ([nodeid for nodeid, _ in entry.executions]
                        if entry.executions else list(entry.nodeids))
            path = Path(configuration_path) if configuration_path else None
            profile = ExecutionProfile(
                name=name or entry.run_name or entry.profile_name or "Recorded run",
                sequence=sequence,
                configuration_name=path.name if path else "",
                configuration_text=path.read_text(encoding="utf-8-sig") if path else "",
                description="Sequence recovered from history; original execution settings were not archived.",
            )
        validate_profile(profile)
        return profile
    except (KeyError, TypeError, AttributeError) as exc:
        raise ProfileValidationError("The archived execution settings are incomplete.") from exc
