"""Macro data: a list of controller states, each held for a duration."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = "s2p-macro"
FORMAT_VERSION = 1
BUTTON_ORDER = (
    "A", "B", "X", "Y", "LB", "RB", "BACK", "START", "GUIDE",
    "L_STK", "R_STK", "UP", "DOWN", "LEFT", "RIGHT",
)
MIN_STEP_MS = 1
MAX_STEP_MS = 600_000
MAX_STEPS = 100_000
NEUTRAL_STICK = (0, 0)


class MacroFormatError(ValueError):
    pass


def canonical_buttons(buttons):
    wanted = {str(name).strip().upper() for name in buttons}
    unknown = wanted.difference(BUTTON_ORDER)
    if unknown:
        raise MacroFormatError(f"unknown button(s): {', '.join(sorted(unknown))}")
    return tuple(name for name in BUTTON_ORDER if name in wanted)


def _int(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise MacroFormatError(f"{label} must be an integer from {low} to {high}")
    return value


def _stick(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MacroFormatError(f"{label} must be [x, y]")
    return (
        _int(value[0], -32768, 32767, label),
        _int(value[1], -32768, 32767, label),
    )


@dataclass(frozen=True)
class Step:
    """One controller state held for ``duration_ms``."""

    duration_ms: int
    buttons: tuple = ()
    lt: int = 0
    rt: int = 0
    left: tuple = NEUTRAL_STICK
    right: tuple = NEUTRAL_STICK

    def __post_init__(self):
        _int(self.duration_ms, MIN_STEP_MS, MAX_STEP_MS, "duration_ms")
        object.__setattr__(self, "buttons", canonical_buttons(self.buttons))
        _int(self.lt, 0, 255, "lt")
        _int(self.rt, 0, 255, "rt")
        object.__setattr__(self, "left", _stick(self.left, "left"))
        object.__setattr__(self, "right", _stick(self.right, "right"))

    @property
    def is_neutral(self):
        return self.same_input(Step(1))

    def same_input(self, other):
        return (self.buttons, self.lt, self.rt, self.left, self.right) == (
            other.buttons, other.lt, other.rt, other.left, other.right
        )

    def uses_stick(self, side):
        return (self.left if side == "left" else self.right) != NEUTRAL_STICK

    def to_dict(self):
        data = {"duration_ms": self.duration_ms, "buttons": list(self.buttons)}
        if self.lt:
            data["lt"] = self.lt
        if self.rt:
            data["rt"] = self.rt
        if self.left != NEUTRAL_STICK:
            data["left"] = list(self.left)
        if self.right != NEUTRAL_STICK:
            data["right"] = list(self.right)
        return data

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise MacroFormatError("each step must be an object")
        buttons = data.get("buttons", [])
        if not isinstance(buttons, list):
            raise MacroFormatError("buttons must be a list")
        return cls(
            duration_ms=data.get("duration_ms"),
            buttons=tuple(buttons),
            lt=data.get("lt", 0),
            rt=data.get("rt", 0),
            # Passed as-is: _stick() validates the shape, so null or a number
            # becomes a MacroFormatError instead of a TypeError from tuple().
            left=data.get("left", NEUTRAL_STICK),
            right=data.get("right", NEUTRAL_STICK),
        )


@dataclass
class Macro:
    name: str
    steps: list = field(default_factory=list)
    # Controller buttons that, held together, start (or stop) this macro.
    trigger: tuple = ()

    @property
    def total_ms(self):
        return sum(step.duration_ms for step in self.steps)

    def sticks_used(self):
        return {
            side for side in ("left", "right")
            if any(step.uses_stick(side) for step in self.steps)
        }

    def to_dict(self):
        data = {
            "format": FORMAT,
            "version": FORMAT_VERSION,
            "name": self.name,
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.trigger:
            data["trigger"] = list(canonical_buttons(self.trigger))
        return data

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise MacroFormatError("not an S2P macro file")
        if data.get("version") != FORMAT_VERSION:
            raise MacroFormatError(f"unsupported macro version {data.get('version')!r}")
        name = str(data.get("name") or "").strip()
        steps = data.get("steps")
        if not name:
            raise MacroFormatError("macro name is missing")
        if not isinstance(steps, list) or len(steps) > MAX_STEPS:
            raise MacroFormatError("steps must be a list")
        trigger = data.get("trigger", [])
        if not isinstance(trigger, list):
            raise MacroFormatError("trigger must be a list of buttons")
        return cls(
            name=name,
            steps=[Step.from_dict(item) for item in steps],
            trigger=canonical_buttons(trigger),
        )


def events_to_steps(events, end_time, keep_trailing_neutral=False):
    """Turn recorded ``(seconds, Step-with-dummy-duration)`` changes into steps.

    Leading neutral time is not recorded by the recorder; a trailing neutral
    state is dropped because playback always releases everything at the end
    (the live preview keeps it so the current release is visible).
    """
    steps = []
    for index, (stamp, state) in enumerate(events):
        until = events[index + 1][0] if index + 1 < len(events) else end_time
        duration = max(MIN_STEP_MS, min(MAX_STEP_MS, round((until - stamp) * 1000)))
        if steps and steps[-1].same_input(state):
            previous = steps[-1]
            steps[-1] = Step(
                min(MAX_STEP_MS, previous.duration_ms + duration),
                previous.buttons, previous.lt, previous.rt, previous.left, previous.right,
            )
            continue
        steps.append(Step(duration, state.buttons, state.lt, state.rt, state.left, state.right))
    while steps and steps[-1].is_neutral and not keep_trailing_neutral:
        steps.pop()
    return steps


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_file_stem(name):
    stem = _UNSAFE.sub("_", str(name)).strip(" .")
    return stem[:80] or "macro"


class MacroLibrary:
    """Macros stored as one JSON file each in ``folder``."""

    def __init__(self, folder):
        self.folder = Path(folder)

    def path_for(self, name):
        return self.folder / f"{safe_file_stem(name)}.json"

    def names(self):
        if not self.folder.is_dir():
            return []
        found = []
        for path in sorted(self.folder.glob("*.json"), key=lambda item: item.stem.lower()):
            try:
                found.append(self.load_file(path).name)
            except (OSError, ValueError):
                continue
        return found

    @staticmethod
    def load_file(path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except ValueError as exc:
            raise MacroFormatError("macro file is not valid JSON") from exc
        try:
            return Macro.from_dict(data)
        except (TypeError, AttributeError, KeyError) as exc:
            # Safety net: any other malformed value is a format error, so
            # Import... shows a message and the macro list skips the file.
            raise MacroFormatError(f"invalid macro file: {exc}") from exc

    def load(self, name):
        return self.load_file(self.path_for(name))

    def exists(self, name):
        return self.path_for(name).exists()

    def save(self, macro):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.write_file(macro, self.path_for(macro.name))

    @staticmethod
    def write_file(macro, path):
        """Atomic write: a crash never leaves a half-written macro."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(macro.to_dict(), ensure_ascii=False, indent=1)
        handle, temp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.replace(temp, path)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise

    def delete(self, name):
        self.path_for(name).unlink(missing_ok=True)

    def triggers(self):
        """``{macro name: trigger buttons}`` for every macro that has one."""
        found = {}
        if not self.folder.is_dir():
            return found
        for path in self.folder.glob("*.json"):
            try:
                macro = self.load_file(path)
            except (OSError, ValueError):
                continue
            if macro.trigger:
                found[macro.name] = macro.trigger
        return found

    def rename(self, old, new):
        macro = self.load(old)
        macro.name = new
        self.save(macro)
        if self.path_for(old) != self.path_for(new):
            self.delete(old)
        return macro
