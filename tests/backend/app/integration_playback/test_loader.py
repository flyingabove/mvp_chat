import types

import backend.app.integration_playback.loader as loader
from backend.app.integration_playback.scenario_registry import list_scenarios, SCENARIOS


def _reset_loaded():
    loader._loaded = False
    SCENARIOS.clear()


def test_loader_handles_missing_package(monkeypatch):
    _reset_loaded()

    def fake_import(name):
        raise ModuleNotFoundError

    monkeypatch.setattr(loader.importlib, "import_module", fake_import)

    loader.ensure_scenarios_loaded()

    assert loader._loaded is True


def test_loader_handles_namespace_package(monkeypatch):
    _reset_loaded()

    dummy_pkg = types.SimpleNamespace(__file__=None)
    iter_called = False

    def fake_import(name):
        return dummy_pkg

    def fake_iter_modules(paths):
        nonlocal iter_called
        iter_called = True
        return []

    monkeypatch.setattr(loader.importlib, "import_module", fake_import)
    monkeypatch.setattr(loader.pkgutil, "iter_modules", fake_iter_modules)

    loader.ensure_scenarios_loaded()

    assert loader._loaded is True
    assert iter_called is False  # should bail out before iter_modules when __file__ is missing


def test_loader_loads_builtin_scenarios():
    _reset_loaded()

    loader.ensure_scenarios_loaded()

    scenarios = list_scenarios()
    assert "epistemic_iu_flow" in scenarios
