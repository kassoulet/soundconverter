#!/usr/bin/python3
# -*- coding: utf-8 -*-


"""Sets up soundconverter for the tests and runs them."""


import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gst, Gio, Gtk, GLib
Gst.init([None] + [a for a in sys.argv[1:] if '-gst' in a])

from soundconverter.util.settings import set_gio_settings
from soundconverter.interface.ui import win, gtk_iteration

# don't overwrite the users settings during tests
backend = Gio.memory_settings_backend_new()
gio_settings = Gio.Settings.new_with_backend('org.soundconverter', backend)
set_gio_settings(gio_settings)

# tests will control gtk main iterations
Gtk.main = gtk_iteration
Gtk.main_quit = lambda: None

# import all the tests and run them
import unittest
# from testcases.integration import *
# from testcases.names import *
# from testcases.format import *
from testcases.taskqueue import *

if __name__ == "__main__":
    unittest.main()
