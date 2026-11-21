"""End to end against S2P-XInput-Lite's real Extensions pipe server.

Needs the S2P-XInput-Lite source next to this repo (or S2P_XINPUT_LITE_SRC).
The physical controller is simulated by merging reports through S2P's hub.
"""

import sys
import time
import unittest
import uuid
from types import SimpleNamespace

import _paths

S2P_SRC = _paths.s2p_source()
if S2P_SRC is not None and str(S2P_SRC) not in sys.path:
    sys.path.insert(0, str(S2P_SRC))

from s2p_ext import ExtensionClient, S2PError  # noqa: E402
from s2p_macro.engine import MacroPlayer, MacroRecorder  # noqa: E402
from s2p_macro.model import Step  # noqa: E402

A, B, X = 0x1000, 0x2000, 0x4000


def report(**values):
    fields = dict(wButtons=0, bLeftTrigger=0, bRightTrigger=0,
                  sThumbLX=0, sThumbLY=0, sThumbRX=0, sThumbRY=0)
    fields.update(values)
    return SimpleNamespace(**fields)


@unittest.skipUnless(sys.platform == "win32" and S2P_SRC is not None, "needs S2P-XInput-Lite on Windows")
class S2PIntegrationTests(unittest.TestCase):
    def setUp(self):
        import extension_bridge as bridge

        self.bridge = bridge
        self.pipe = rf"\\.\pipe\S2P-Extensions-test-{uuid.uuid4().hex}"
        xinput = SimpleNamespace(set_extension_input=lambda hub: None)
        self.manager = bridge.ExtensionManager(xinput, pipe_name=self.pipe)
        self.manager.launch_tool = lambda tool_id, reopen=False, background=False: True
        self.manager._launch_tokens["macro-token"] = "macro"
        self.addCleanup(self.manager.close)

    def enable(self, **options):
        self.manager.apply(self.bridge.ExtensionSettings((
            self.bridge.ToolSettings("macro", r"C:\S2P-Joystick-Macro.exe", **options),
        )))

    def client(self, **options):
        client = ExtensionClient("S2P-Joystick-Macro", "test", pipe_name=self.pipe,
                                 token="macro-token", **options)
        self.addCleanup(client.close)
        return client

    def physical_frame(self, **values):
        frame = report(**values)
        self.manager._hub.merge_into(frame)
        return frame

    def test_played_macro_merges_with_physical_input(self):
        self.enable()
        client = self.client(sticks=("left",))
        self.assertEqual(client.connect()["capabilities"], ["input"])
        seen = []

        def send(step, sticks):
            client.send_state(step.buttons, lt=step.lt, rt=step.rt,
                              left=step.left if "left" in sticks else None)

        player = MacroPlayer(send, client.release_all)
        player.play([Step(150, ("A",), rt=200), Step(150, ("B",), left=(0, 30000))],
                    sticks=client.granted_sticks)
        deadline = time.monotonic() + 2
        while player.running and time.monotonic() < deadline:
            frame = self.physical_frame(wButtons=X)  # player holds X on the real pad
            seen.append((frame.wButtons, frame.bRightTrigger, frame.sThumbLY))
            time.sleep(0.004)
        self.assertIn((X | A, 200, 0), seen)
        self.assertIn((X | B, 0, 30000), seen)
        time.sleep(0.05)
        final = self.physical_frame(wButtons=X)
        # Playback ended: the tool's input is gone, the physical X stays.
        self.assertEqual((final.wButtons, final.sThumbLY), (X, 0))

    def test_recording_reads_physical_output_only(self):
        self.enable(allow_read=True)
        client = self.client(capabilities=("input", "read"))
        self.assertEqual(set(client.connect()["capabilities"]), {"input", "read"})
        recorder = MacroRecorder(client.get_input, poll_seconds=0.002)
        recorder.start()
        client.send_state(["Y"])  # the tool's own output must not be recorded
        for buttons, frames in ((A, 30), (A | B, 30), (0, 10)):
            for _ in range(frames):
                self.physical_frame(wButtons=buttons)
                time.sleep(0.003)
        steps = recorder.stop()
        self.assertIsNone(recorder.error)
        self.assertEqual([step.buttons for step in steps], [("A",), ("A", "B")])
        self.assertGreater(steps[0].duration_ms, 50)

    def test_controller_trigger_starts_a_macro_through_s2p(self):
        from s2p_macro.engine import TriggerMonitor

        self.enable(allow_read=True)
        client = self.client(capabilities=("input", "read"))
        client.connect()
        fired = []
        monitor = TriggerMonitor(client.get_input, fired.append, poll_seconds=0.002)
        monitor.set_triggers({"Dash": ("BACK", "Y")})
        monitor.start()
        self.addCleanup(monitor.stop)
        BACK, Y = 0x0020, 0x8000
        for buttons, frames in ((BACK, 10), (BACK | Y, 10), (0, 5)):
            for _ in range(frames):
                self.physical_frame(wButtons=buttons)
                time.sleep(0.004)
        self.assertEqual(fired, ["Dash"])

    def test_record_without_read_permission_is_refused(self):
        self.enable()  # read not allowed in S2P
        client = self.client(capabilities=("input", "read"))
        self.assertEqual(client.connect()["capabilities"], ["input"])
        with self.assertRaises(S2PError) as caught:
            client.get_input()
        self.assertEqual(caught.exception.code, "permission_denied")
        self.assertFalse(client.connected)

    def test_permission_change_reconnects_automatically(self):
        from s2p_ext import AutoConnection

        self.enable()
        states = []
        connection = AutoConnection(
            lambda: ExtensionClient("S2P-Joystick-Macro", pipe_name=self.pipe,
                                    token="macro-token", capabilities=("input", "read")),
            on_change=lambda state, detail: states.append(state),
            retry_seconds=0.1,
        )
        connection.start()
        self.addCleanup(connection.stop)
        deadline = time.monotonic() + 3
        while connection.client is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(connection.client.granted, {"input"})
        first = connection.client
        # The user allows "read" in S2P: S2P drops the session and the tool
        # notices (keepalive ping) and reconnects with the new permission.
        self.enable(allow_read=True)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            client = connection.client
            if client is not None and client is not first and "read" in client.granted:
                break
            time.sleep(0.05)
        self.assertIsNot(connection.client, first)
        self.assertEqual(connection.client.granted, {"input", "read"})
        entry = self.manager.status()["tools"]["macro"]
        self.assertEqual(entry["state"], "connected")

    def test_tool_follows_the_s2p_window_process(self):
        import subprocess
        import threading
        from s2p_ext import AutoConnection

        # A stand-in for the S2P window process that we can end on demand.
        host = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: host.poll() is None and host.kill())
        self.manager.host_pid = host.pid
        self.enable()
        exited = threading.Event()
        connection = AutoConnection(
            lambda: ExtensionClient("S2P-Joystick-Macro", pipe_name=self.pipe, token="macro-token"),
            retry_seconds=0.1, on_host_exit=exited.set,
        )
        connection.start()
        self.addCleanup(connection.stop)
        deadline = time.monotonic() + 3
        while connection.client is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(connection.client.welcome["host_pid"], host.pid)
        self.assertFalse(exited.wait(0.3))
        host.kill()
        self.assertTrue(exited.wait(3.0))

    def test_unknown_tool_is_rejected(self):
        self.enable()
        client = ExtensionClient("S2P-Joystick-Macro", pipe_name=self.pipe, token="wrong")
        with self.assertRaises(S2PError) as caught:
            client.connect()
        self.assertEqual(caught.exception.code, "unauthorized")


if __name__ == "__main__":
    unittest.main()
