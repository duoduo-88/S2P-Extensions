"""Put the SDK and the macro package on sys.path for the tests."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "sdk", ROOT / "macro"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


def s2p_source():
    """S2P-XInput-Lite's src/ for integration tests, or None."""
    configured = os.environ.get("S2P_XINPUT_LITE_SRC")
    candidates = [Path(configured)] if configured else []
    candidates.append(ROOT.parent / "S2P-XInput-Lite" / "src")
    for candidate in candidates:
        if (candidate / "extension_bridge.py").is_file():
            return candidate
    return None
