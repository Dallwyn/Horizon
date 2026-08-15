"""Reporting-timezone configuration and the run date derived from it."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.models import AIConfig, Config, SourcesConfig
from src.orchestrator import HorizonOrchestrator


def make_config(**kwargs) -> Config:
    return Config(
        ai=AIConfig(provider="openai", model="test", api_key_env="TEST_API_KEY"),
        sources=SourcesConfig(),
        **kwargs,
    )


def test_report_timezone_defaults_to_utc() -> None:
    assert make_config().report_timezone == "UTC"


def test_report_timezone_accepts_iana_name() -> None:
    assert make_config(report_timezone="Europe/Berlin").report_timezone == "Europe/Berlin"


@pytest.mark.parametrize("value", ["Not/AZone", "CEST", ""])
def test_report_timezone_rejects_invalid_names(value) -> None:
    with pytest.raises(ValidationError, match="not a valid IANA timezone"):
        make_config(report_timezone=value)


def _report_date_for(timezone_name: str) -> str:
    orchestrator = HorizonOrchestrator.__new__(HorizonOrchestrator)
    orchestrator.config = SimpleNamespace(report_timezone=timezone_name)
    return orchestrator._report_date()


def test_report_date_uses_configured_timezone() -> None:
    assert _report_date_for("Europe/Berlin") == datetime.now(
        ZoneInfo("Europe/Berlin")
    ).strftime("%Y-%m-%d")


def test_report_date_can_differ_from_utc_across_a_day_boundary() -> None:
    """Guards the actual point of the setting: a run near the UTC boundary must
    be labelled with the reader's calendar day, not UTC's."""
    utc_date = _report_date_for("UTC")
    kiritimati_date = _report_date_for("Pacific/Kiritimati")  # UTC+14
    midway_date = _report_date_for("Pacific/Midway")  # UTC-11

    assert midway_date <= utc_date <= kiritimati_date
    assert midway_date != kiritimati_date


def test_report_date_falls_back_to_utc_when_config_lacks_the_field() -> None:
    """Configs built before the field existed (and test doubles) must not crash."""
    orchestrator = HorizonOrchestrator.__new__(HorizonOrchestrator)
    orchestrator.config = SimpleNamespace()

    assert orchestrator._report_date() == datetime.now(ZoneInfo("UTC")).strftime(
        "%Y-%m-%d"
    )
