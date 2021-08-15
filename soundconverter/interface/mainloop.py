#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2020 Gautier Portet
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA

import time

from gi.repository import Gtk, GLib


def idle(func):
    def callback(*args, **kwargs):
        GLib.idle_add(func, *args, **kwargs)
    return callback


def gtk_iteration(blocking=False):
    """Keeps the UI and event loops for gst going.

    Paramters
    ---------
    blocking : bool
        If True, will call main_iteration even if no events are pending,
        which will wait until an event is available.
    """
    if blocking:
        while True:
            Gtk.main_iteration()
            if not Gtk.events_pending():
                break
    else:
        while Gtk.events_pending():
            Gtk.main_iteration()


def gtk_sleep(duration):
    """Sleep while keeping the GUI responsive."""
    start = time.time()
    while time.time() < start + duration:
        time.sleep(0.01)
        gtk_iteration()
