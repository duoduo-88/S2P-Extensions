"""Recording (via S2P "read") and playback (via S2P "input") of macros."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from contextlib import contextmanager

from .model import MAX_STEP_MS, Step, canonical_buttons, events_to_steps

HEARTBEAT_SECONDS = 0.25   # S2P clears silent input after 1 s
POLL_SECONDS = 0.004        # ~250 Hz, at or above S2P's input report rate
DEFAULT_LOOP_GAP_MS = 50    # neutral gap so repeated presses are separate presses
DEFAULT_STICK_DEADZONE = 1200
# Reports skipped while reading on time only mean the controller reports
# faster than POLL_SECONDS (500/1000 Hz pads); a change that short is not
# something a game reliably sees either.  Skipped reports count as missed
# only when two reads were further apart than this (the recorder stalled).
MISSED_GAP_SECONDS = 0.02


@contextmanager
def fine_timer():
    """1 ms Windows timer resolution, only while recording or playing."""
    winmm = None
    if sys.platform == "win32":
        try:
            winmm = ctypes.WinDLL("winmm")
            winmm.timeBeginPeriod(1)
        except OSError:
            winmm = None
    try:
        yield
    finally:
        if winmm is not None:
            winmm.timeEndPeriod(1)


def state_from_input(reply, record_sticks, deadzone=DEFAULT_STICK_DEADZONE):
    """Convert an S2P ``get_input`` reply into a Step (duration filled later)."""

    def stick(x_key, y_key):
        if not record_sticks:
            return (0, 0)
        x, y = int(reply.get(x_key, 0)), int(reply.get(y_key, 0))
        if abs(x) < deadzone and abs(y) < deadzone:
            return (0, 0)
        return (x, y)

    return Step(
        1,
        canonical_buttons(reply.get("buttons", ())),
        int(reply.get("lt", 0)),
        int(reply.get("rt", 0)),
        stick("lx", "ly"),
        stick("rx", "ry"),
    )


class MacroRecorder:
    """Poll S2P's pre-merge output and keep every change with its time.

    Recording starts at the first non-neutral input after ``start()`` so idle
    time before the first press is not stored.
    """

    def __init__(self, get_input, record_sticks=False, clock=time.perf_counter,
                 poll_seconds=POLL_SECONDS, deadzone=DEFAULT_STICK_DEADZONE):
        self._get_input = get_input
        self._record_sticks = record_sticks
        self._clock = clock
        self._poll = poll_seconds
        self._deadzone = deadzone
        self._stop = threading.Event()
        self._thread = None
        self._events = []
        self._end_time = None
        self.error = None
        self.first_input_at = None
        # get_input returns S2P's latest report, not a queue.  S2P numbers its
        # reports, so a jump in "frame" across a stall (reads more than
        # MISSED_GAP_SECONDS apart) counts the reports that were never seen
        # (counted only once recording has started).
        self.frames_seen = 0
        self.frames_missed = 0

    @property
    def frames_total(self):
        return self.frames_seen + self.frames_missed

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def elapsed(self):
        if self.first_input_at is None:
            return 0.0
        end = self._end_time if self._end_time is not None else self._clock()
        return max(0.0, end - self.first_input_at)

    @property
    def change_count(self):
        return len(self._events)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="S2P-MacroRecorder", daemon=True)
        self._thread.start()

    def preview_steps(self):
        """Steps recorded so far, for showing the recording live."""
        events = list(self._events)  # appended by the recording thread
        end = self._end_time if self._end_time is not None else self._clock()
        return events_to_steps(events, end, keep_trailing_neutral=True)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
        if self._end_time is None:
            self._end_time = self._clock()
        return events_to_steps(self._events, self._end_time)

    def _run(self):
        last_frame = None
        last_state = None
        last_read = None
        with fine_timer():
            while not self._stop.is_set():
                try:
                    reply = self._get_input()
                except Exception as exc:  # S2P closed, permission lost, ...
                    self.error = exc
                    break
                now = self._clock()
                stalled = last_read is not None and now - last_read > MISSED_GAP_SECONDS
                last_read = now
                frame = reply.get("frame", 0)
                if frame and frame != last_frame:
                    if self._events and stalled and last_frame is not None and frame > last_frame:
                        self.frames_missed += frame - last_frame - 1
                    last_frame = frame  # a lower number: S2P restarted, no gap
                    state = state_from_input(reply, self._record_sticks, self._deadzone)
                    if last_state is None or not state.same_input(last_state):
                        if self._events or not state.is_neutral:
                            if self.first_input_at is None:
                                self.first_input_at = now
                            self._events.append((now, state))
                        last_state = state
                    if self._events:
                        self.frames_seen += 1
                self._stop.wait(self._poll)
        self._end_time = self._clock()


class MacroPlayer:
    """Send each step's state for its duration on an absolute schedule.

    ``send(step, sticks)`` and ``release()`` talk to S2P.  The current state
    is resent every HEARTBEAT_SECONDS so S2P never times it out, and
    everything is released when playback ends, is stopped, or fails.
    """

    def __init__(self, send, release, clock=time.perf_counter):
        self._send = send
        self._release = release
        self._clock = clock
        self._stop = threading.Event()
        self._thread = None
        self.error = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def play(self, steps, loops=1, speed=1.0, sticks=frozenset(),
             loop_gap_ms=DEFAULT_LOOP_GAP_MS, on_progress=None, on_finished=None):
        if self.running:
            raise RuntimeError("already playing")
        if not steps:
            raise ValueError("the macro has no steps")
        if not 0.1 <= float(speed) <= 10.0:
            raise ValueError("speed must be between 0.1 and 10")
        self._stop.clear()
        self.error = None
        self._thread = threading.Thread(
            target=self._run,
            args=(list(steps), int(loops), float(speed), frozenset(sticks),
                  max(0, int(loop_gap_ms)), on_progress, on_finished),
            name="S2P-MacroPlayer", daemon=True,
        )
        self._thread.start()

    def stop(self, wait=True):
        self._stop.set()
        if wait and self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(2.0)

    def _hold(self, step, sticks, until):
        """Keep ``step`` applied until ``until``; False when stopped."""
        self._send(step, sticks)
        next_beat = self._clock() + HEARTBEAT_SECONDS
        while True:
            now = self._clock()
            if now >= until:
                return True
            if now >= next_beat:
                self._send(step, sticks)
                next_beat = now + HEARTBEAT_SECONDS
            if self._stop.wait(min(until, next_beat) - now):
                return False

    def _run(self, steps, loops, speed, sticks, loop_gap_ms, on_progress, on_finished):
        gap = Step(max(1, loop_gap_ms)) if loop_gap_ms else None
        completed = 0
        try:
            with fine_timer():
                deadline = self._clock()
                loop = 0
                while loops <= 0 or loop < loops:
                    loop += 1
                    for index, step in enumerate(steps):
                        if on_progress is not None:
                            on_progress(loop, index)
                        duration = min(MAX_STEP_MS, step.duration_ms) / 1000.0 / speed
                        deadline += duration
                        if not self._hold(step, sticks, deadline):
                            return
                    completed = loop
                    more = loops <= 0 or loop < loops
                    if more and gap is not None:
                        deadline += gap.duration_ms / 1000.0
                        if not self._hold(gap, sticks, deadline):
                            return
        except Exception as exc:  # S2P went away mid-playback
            self.error = exc
        finally:
            try:
                self._release()
            except Exception:
                pass
            if on_finished is not None:
                on_finished(completed, self.error)


TRIGGER_POLL_SECONDS = 0.01


class TriggerMonitor:
    """Watch S2P's pre-merge output for macro trigger combinations.

    ``on_trigger(name)`` is called from this thread on the rising edge of a
    combination (every button held, which was not the case one frame
    earlier).  When several combinations match, the largest one wins, so
    BACK+Y+X is not also reported as BACK+Y.
    """

    def __init__(self, get_input, on_trigger, poll_seconds=TRIGGER_POLL_SECONDS):
        self._get_input = get_input
        self._on_trigger = on_trigger
        self._poll = poll_seconds
        self._triggers = {}
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        self.source = get_input

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def set_triggers(self, triggers):
        self._triggers = {name: frozenset(buttons) for name, buttons in triggers.items() if buttons}

    def start(self):
        self._thread = threading.Thread(target=self._run, name="S2P-MacroTrigger", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(1.0)

    _held_before = frozenset()
    _last_frame = None

    def process(self, reply):
        """Handle one ``get_input`` reply; return the triggered macro name or None."""
        frame = reply.get("frame", 0)
        if not frame or frame == self._last_frame:
            return None
        self._last_frame = frame
        held = frozenset(reply.get("buttons", ()))
        held_before, self._held_before = self._held_before, held
        matches = [
            (len(buttons), name) for name, buttons in self._triggers.items()
            if buttons <= held and not buttons <= held_before
        ]
        return max(matches)[1] if matches else None

    def _run(self):
        while not self._stop.is_set():
            try:
                reply = self._get_input()
            except Exception as exc:  # S2P went away; the app restarts us
                self.error = exc
                return
            name = self.process(reply)
            if name is not None:
                self._on_trigger(name)
            self._stop.wait(self._poll)
