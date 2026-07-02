import builtins

from main import resolve_run_mode


def test_resolve_run_mode_prefers_cli_over_env():
    run_mode = resolve_run_mode(["--mode", "5"], {"RUN_MODE": "3"})

    assert run_mode == "5"


def test_resolve_run_mode_uses_env_when_cli_missing():
    run_mode = resolve_run_mode([], {"RUN_MODE": "5"})

    assert run_mode == "5"


def test_resolve_run_mode_prompts_when_cli_and_env_missing(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _prompt: "5")

    run_mode = resolve_run_mode([], {})

    assert run_mode == "5"
