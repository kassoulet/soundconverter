#!/usr/bin/python3
# -*- coding: utf-8 -*-


"""Sets up soundconverter for the tests and runs them."""


import sys
import unittest

import gi
gi.require_version('GstPbutils', '1.0')
gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gst, Gio, Gtk, GLib
Gst.init(sys.argv)

from soundconverter.util.settings import set_gio_settings
from soundconverter.interface.ui import gtk_iteration

# don't overwrite the users settings during tests
backend = Gio.memory_settings_backend_new()
gio_settings = Gio.Settings.new_with_backend('org.soundconverter', backend)
set_gio_settings(gio_settings)

# tests will control gtk main iterations for the ui
Gtk.main = gtk_iteration
Gtk.main_quit = lambda: None

if __name__ == "__main__":
    testsuite = unittest.TestLoader().discover('testcases', pattern='*.py')
    unittest.TextTestRunner(verbosity=1).run(testsuite)
