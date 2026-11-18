"""Where the macro tool keeps its files, and its small settings file."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
# How often the game reads the controller (not its frame rate) -> the shortest
# step it always reads: about two reads, measured in docs/playback-timing.md.
GAME_INPUT_RATES = {30: 66, 60: 33, 144: 16}
DEFAULT_GAME_INPUT_HZ = 60


def data_directory():
    """Next to the EXE when packaged (portable), else the macro/ folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


@dataclass
class AppSettings:
    language: str = "zh"
    notice_accepted: bool = False
    loops: int = 1
    speed: float = 1.0
    loop_gap_ms: int = 50
    record_sticks: bool = False
    trigger_enabled: bool = True
    tray_hint_shown: bool = False
    last_macro: str = ""
    game_input_hz: int = DEFAULT_GAME_INPUT_HZ

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        settings = cls()
        for item in fields(cls):
            value = data.get(item.name, getattr(settings, item.name))
            if isinstance(value, type(getattr(settings, item.name))) or (
                item.type == "float" and isinstance(value, int) and not isinstance(value, bool)
            ):
                setattr(settings, item.name, value)
        if settings.language not in ("zh", "en"):
            settings.language = "zh"
        settings.loops = max(0, min(9999, int(settings.loops)))
        settings.loop_gap_ms = max(0, min(5000, int(settings.loop_gap_ms)))
        if float(settings.speed) not in SPEEDS:
            settings.speed = 1.0
        if settings.game_input_hz not in GAME_INPUT_RATES:
            settings.game_input_hz = DEFAULT_GAME_INPUT_HZ
        return settings

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(asdict(self), stream, ensure_ascii=False, indent=1)
            os.replace(temp, path)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
