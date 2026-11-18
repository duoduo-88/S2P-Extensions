import os
import sys
import threading
import unittest

import _paths  # noqa: F401

from s2p_ext import AutoConnection, ProcessExitWatcher


class HostWatcherTests(unittest.TestCase):
    def test_no_watcher_is_left_behind_after_stop(self):
        # A connect that finishes after stop() must not start a new watcher.
        connection = AutoConnection(lambda: None, on_host_exit=lambda: None)
        connection.stop()
        connection._watch_host(os.getpid())
        self.assertIsNone(connection._host_watcher)

    def test_same_host_keeps_one_watcher(self):
        connection = AutoConnection(lambda: None, on_host_exit=lambda: None)
        self.addCleanup(connection.stop)
        connection._watch_host(os.getpid())
        first = connection._host_watcher
        connection._watch_host(os.getpid())  # a reconnect to the same S2P
        self.assertIs(connection._host_watcher, first)

    @unittest.skipUnless(sys.platform == "win32", "Windows process handles")
    def test_stopping_a_watcher_does_not_report_an_exit(self):
        fired = threading.Event()
        watcher = ProcessExitWatcher(os.getpid(), fired.set)
        self.assertTrue(watcher.start())
        watcher.stop()
        self.assertFalse(fired.wait(0.2))


if __name__ == "__main__":
    unittest.main()
