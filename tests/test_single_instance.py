import sys
import threading
import unittest
import uuid

import _paths  # noqa: F401

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


if __name__ == "__main__":
    unittest.main()
