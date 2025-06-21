#!/usr/bin/python3


"""Sets up soundconverter for the tests and runs them."""

import sys
import unittest

import gi

gi.require_version("GstPbutils", "1.0")
gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gst, Gtk, Gio  # noqa: E402, F401, I001

args = Gst.init(sys.argv)

from soundconverter.interface.mainloop import gtk_iteration  # noqa: E402
from soundconverter.util.settings import set_gio_settings  # noqa: E402

# don't overwrite the users settings during tests
backend = Gio.memory_settings_backend_new()
gio_settings = Gio.Settings.new_with_backend("org.soundconverter", backend)
set_gio_settings(gio_settings)

# tests will control gtk main iterations for the ui
Gtk.main = gtk_iteration
Gtk.main_quit = lambda: None

if __name__ == "__main__":
    modules = args[1:]
    # discoverer is really convenient, but it can't find a specific test
    # in all of the available tests like unittest.main() does...,
    # so provide both options.
    if len(modules) > 0:
        # for example `python3 tests/test.py discoverer.DiscovererTest.test_read_tags`
        testsuite = unittest.defaultTestLoader.loadTestsFromNames(
            [f"testcases.{module}" for module in modules]
        )
    else:
        # run all tests by default
        testsuite = unittest.defaultTestLoader.discover("testcases", pattern="*.py")

    testrunner = unittest.TextTestRunner(verbosity=2).run(testsuite)
