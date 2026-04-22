"""Tests for the thin top-level CLI wrapper."""

from __future__ import annotations

import main


def test_cli_defaults_to_siting_for_legacy_root_invocation(monkeypatch):
    calls = {}

    def fake_run_siting_pipeline(*, n_hubs: int, skip_street_network: bool) -> None:
        calls["n_hubs"] = n_hubs
        calls["skip_street_network"] = skip_street_network

    monkeypatch.setattr(main, "run_siting_pipeline", fake_run_siting_pipeline)
    assert main.cli(["--hubs", "8", "--skip-street-network"]) == 0
    assert calls == {"n_hubs": 8, "skip_street_network": True}


def test_cli_dispatches_named_commands(monkeypatch):
    calls = {}

    def fake_run_corridor_report(*, top_n: int, sim_hour: int) -> None:
        calls["top_n"] = top_n
        calls["sim_hour"] = sim_hour

    monkeypatch.setattr(main, "run_corridor_report", fake_run_corridor_report)
    assert main.cli(["corridors", "--top-n", "5", "--sim-hour", "12"]) == 0
    assert calls == {"top_n": 5, "sim_hour": 12}
