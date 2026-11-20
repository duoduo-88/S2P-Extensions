import os
import sys
import threading
import unittest
import uuid
from unittest.mock import patch

import _paths  # noqa: F401

from s2p_macro import single_instance
from s2p_macro.single_instance import SingleInstance


@unittest.skipUnless(sys.platform == "win32", "Windows named events")
class SingleInstanceTests(unittest.TestCase):
    def test_second_launch_wakes_the_first_and_exits(self):
        name = f"Local\\S2P-Joystick-Macro.test-{uuid.uuid4().hex}"
        shown = threading.Event()
        first = SingleInstance(shown.set, name=name)
        self.assertTrue(first.acquire())
        self.addCleanup(first.release)
        second = SingleInstance(lambda: None, name=name)
        self.assertFalse(second.acquire())
        self.assertTrue(shown.wait(2.0))
        # After the first copy quits, a new launch becomes the primary again.
        first.release()
        third = SingleInstance(lambda: None, name=name)
        self.assertTrue(third.acquire())
        third.release()

    def test_second_launch_hands_the_foreground_to_the_running_copy_only(self):
        name = f"Local\\S2P-Joystick-Macro.test-{uuid.uuid4().hex}"
        first = SingleInstance(lambda: None, name=name)
        self.assertTrue(first.acquire())
        self.addCleanup(first.release)
        second = SingleInstance(lambda: None, name=name)
        with patch.object(single_instance, "allow_foreground_handoff") as handoff:
            self.assertFalse(second.acquire())
        # Both copies run in this test process, so the published id is ours.
        handoff.assert_called_once_with(os.getpid())


if __name__ == "__main__":
    unittest.main()
