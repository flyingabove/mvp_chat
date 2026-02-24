"""Auto-load integration playback scenarios.

This loads scenario modules from packaged playback scenarios and test modules
that define IntegrationScenario subclasses. Scenario classes auto-register on
import via IntegrationScenario.__init_subclass__.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
import sys

_loaded = False


def _import_scenarios(
    package_name: str,
    prefixes: tuple[str, ...] = ("scenario_", "test_"),
    *,
    force_reload: bool = False,
) -> None:
    try:
        pkg = importlib.import_module(package_name)
    except ModuleNotFoundError:
        return

    pkg_file = getattr(pkg, "__file__", None)
    if not pkg_file:
        return

    pkg_path = Path(pkg_file).parent
    for mod in pkgutil.iter_modules([str(pkg_path)]):
        if any(mod.name.startswith(p) for p in prefixes):
            mod_name = f"{package_name}.{mod.name}"
            loaded = importlib.import_module(mod_name)
            if force_reload:
                importlib.reload(loaded)


def ensure_scenarios_loaded() -> None:
    global _loaded
    force_reload = False
    if _loaded:
        from backend.app.integration_playback.scenario_registry import SCENARIOS

        if SCENARIOS:
            return
        force_reload = True

    # Ensure project root is on sys.path so the tests package is importable
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.append(str(root))

    # Load built-in packaged scenarios (always shipped with app code)
    _import_scenarios("backend.app.integration_playback.scenarios", force_reload=force_reload)

    # Load test scenarios when present (dev/test only)
    _import_scenarios("tests.backend.integration", force_reload=force_reload)  # legacy path
    _import_scenarios("tests.backend.app.api", force_reload=force_reload)
    _import_scenarios("tests.backend.app.config", force_reload=force_reload)
    _import_scenarios("tests.backend.app.engine", force_reload=force_reload)
    _import_scenarios("tests.backend.app.engine.extractors", force_reload=force_reload)
    _import_scenarios("tests.backend.app.knowledge", force_reload=force_reload)

    _loaded = True
