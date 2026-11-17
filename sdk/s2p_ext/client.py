"""Pipe client for S2P-XInput-Lite Extensions protocol v1."""

from __future__ import annotations

import json
import os
import threading
import time

PROTOCOL_VERSION = 1
DEFAULT_PIPE = r"\\.\pipe\S2P-XInput-Lite.Extensions"
# S2P clears a tool's held input after 1000 ms of silence; resend well inside it.
HEARTBEAT_SECONDS = 0.25
BUTTON_NAMES = (
    "A", "B", "X", "Y", "LB", "RB", "BACK", "START", "GUIDE",
    "L_STK", "R_STK", "UP", "DOWN", "LEFT", "RIGHT",
)


class S2PError(Exception):
    """S2P refused a request; ``code`` is the protocol error code."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ExtensionClient:
    """One connection to S2P.  Thread-safe: senders and requests share a lock."""

    def __init__(
        self, name, version="", capabilities=("input",), sticks=(),
        pipe_name=None, token=None,
    ):
        self.name = name
        self.version = version
        self.capabilities = list(capabilities)
        self.sticks = list(sticks)
        self.pipe_name = pipe_name or os.environ.get("S2P_EXTENSION_PIPE") or DEFAULT_PIPE
        self.token = token if token is not None else os.environ.get("S2P_EXTENSION_TOKEN")
        self.welcome = None
        self._pipe = None
        self._lock = threading.Lock()

    # -- connection -----------------------------------------------------------

    @property
    def connected(self):
        return self._pipe is not None

    @property
    def granted(self):
        return set((self.welcome or {}).get("capabilities", ()))

    @property
    def granted_sticks(self):
        return set((self.welcome or {}).get("sticks", ()))

    def connect(self):
        """Open the pipe and handshake.  OSError: S2P not reachable."""
        pipe = open(self.pipe_name, "r+b", buffering=0)  # each write() = one message
        self._pipe = pipe
        hello = {
            "type": "hello", "protocol": PROTOCOL_VERSION, "name": self.name,
            "version": self.version, "capabilities": self.capabilities,
            "sticks": self.sticks,
        }
        if self.token:
            hello["token"] = self.token
        try:
            reply = self._exchange(hello)
        except Exception:
            self._drop()
            raise
        if reply.get("type") != "welcome":
            self._drop()
            raise S2PError(str(reply.get("code") or "rejected"), str(reply.get("detail") or ""))
        self.welcome = reply
        return reply

    def close(self):
        if self._pipe is None:
            return
        try:
            self._send({"type": "bye"})
        except OSError:
            pass
        self._drop()

    def _drop(self):
        pipe, self._pipe = self._pipe, None
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass

    # -- low level --------------------------------------------------------------

    def _send(self, message):
        pipe = self._pipe
        if pipe is None:
            raise ConnectionError("not connected to S2P")
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            try:
                pipe.write(data)
            except OSError:
                self._drop()
                raise

    def _receive_locked(self):
        raw = self._pipe.read(4096)
        if not raw:
            raise ConnectionError("S2P closed the connection")
        line = raw.decode("utf-8").splitlines()[0]
        return json.loads(line)

    def _exchange(self, message):
        """Send a request and read its reply as one atomic step."""
        pipe = self._pipe
        if pipe is None:
            raise ConnectionError("not connected to S2P")
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            try:
                pipe.write(data)
                reply = self._receive_locked()
            except (OSError, ValueError):
                self._drop()
                raise
        if reply.get("type") == "error":
            self._drop()  # S2P closes the session after any error
            raise S2PError(str(reply.get("code")), str(reply.get("detail") or ""))
        return reply

    # -- protocol ---------------------------------------------------------------

    def send_state(self, buttons=(), lt=None, rt=None, left=None, right=None):
        message = {"type": "state", "buttons": list(buttons)}
        if lt is not None:
            message["lt"] = int(lt)
        if rt is not None:
            message["rt"] = int(rt)
        if left is not None:
            message["lx"], message["ly"] = int(left[0]), int(left[1])
        if right is not None:
            message["rx"], message["ry"] = int(right[0]), int(right[1])
        self._send(message)

    def release_all(self):
        self._send({"type": "release_all"})

    def ping(self, seq=0):
        return self._exchange({"type": "ping", "seq": seq})

    def get_input(self):
        """S2P's own output before any extension merge (needs "read")."""
        return self._exchange({"type": "get_input"})

    def get_controller(self):
        return self._exchange({"type": "get_controller"})


class AutoConnection:
    """Keep one client connected, retrying while S2P is not running.

    ``factory()`` builds a fresh ``ExtensionClient``.  ``on_change(state,
    detail)`` reports "connecting", "connected" or "rejected" from the
    background thread.  A rejection (S2PError) is retried more slowly so a
    misconfigured tool does not spam S2P.
    """

    KEEPALIVE_SECONDS = 1.0

    def __init__(self, factory, on_change=None, retry_seconds=1.0, rejected_retry_seconds=5.0):
        self._factory = factory
        self._on_change = on_change or (lambda state, detail: None)
        self._retry = retry_seconds
        self._rejected_retry = rejected_retry_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self.client = None
        self.state = "connecting"
        self.detail = ""

    def start(self):
        self._thread = threading.Thread(target=self._run, name="S2P-AutoConnection", daemon=True)
        self._thread.start()

    def reconnect(self):
        """Drop the current session (e.g. after changing stick claims)."""
        client, self.client = self.client, None
        if client is not None:
            client.close()
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()
        client, self.client = self.client, None
        if client is not None:
            client.close()
        if self._thread is not None:
            self._thread.join(2.0)

    def _report(self, state, detail=""):
        self.state, self.detail = state, detail
        self._on_change(state, detail)

    def _run(self):
        self._report("connecting")
        next_ping = 0.0
        while not self._stop.is_set():
            client = self.client
            if client is not None and client.connected:
                # A cheap ping notices when S2P ended the session (for example
                # after its permissions changed) so we reconnect by ourselves.
                if time.monotonic() >= next_ping:
                    next_ping = time.monotonic() + self.KEEPALIVE_SECONDS
                    try:
                        client.ping()
                    except (OSError, ValueError, ConnectionError, S2PError):
                        continue  # the client dropped its pipe; reconnect now
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            if client is not None:
                self.client = None
                self._report("connecting")
            candidate = self._factory()
            delay = self._retry
            try:
                candidate.connect()
            except S2PError as exc:
                self._report("rejected", exc.code)
                delay = self._rejected_retry
            except (OSError, ValueError, ConnectionError):
                if self.state != "connecting":
                    self._report("connecting")
            else:
                if self._stop.is_set():
                    candidate.close()
                    break
                self.client = candidate
                self._report("connected")
                continue
            self._wake.wait(delay)
            self._wake.clear()
