"""Entry point: ``python -m s2p_macro`` from macro/, or the packaged EXE."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    # Running from source: make the shared SDK importable.
    sdk = Path(__file__).resolve().parents[2] / "sdk"
    if str(sdk) not in sys.path:
        sys.path.insert(0, str(sdk))

from s2p_macro.app import main  # noqa: E402

if __name__ == "__main__":
    main()
