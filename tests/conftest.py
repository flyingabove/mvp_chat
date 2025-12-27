from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable when running tests outside Docker.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
