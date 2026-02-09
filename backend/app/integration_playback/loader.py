"""Auto-load integration playback scenarios.

This scans the tests/backend/integration/ package for modules named
test_*.py (or legacy scenario_*.py) that register IntegrationScenario
subclasses on import.  This keeps the frontend simple: the backend
maintains the registry.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
import sys

_loaded = False


def _import_scenarios(package_name: str, prefixes: tuple[str, ...] = ("scenario_", "test_")) -> None:
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
            importlib.import_module(f"{package_name}.{mod.name}")


def ensure_scenarios_loaded() -> None:
    global _loaded
    if _loaded:
        return

    # Ensure project root is on sys.path so the tests package is importable
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.append(str(root))

    # Load built-in packaged scenarios (always shipped with app code)
    _import_scenarios("backend.app.integration_playback.scenarios")

    # Load test scenarios when present (dev/test only)
    _import_scenarios("tests.backend.integration")

    _loaded = True
