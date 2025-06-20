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


from gi.repository import GObject


class Task(GObject.Object):
    """Abstract class of a single task."""

    def __init__(self):
        super().__init__()

    # avoid storing a variable called timer in your inheriting class
    def get_progress(self):
        """Fraction of how much of the task is completed.

        Returns a tuple of (progress, weight), because some tasks may
        take longer than others (because it processes more audio), which
        cannot be reflected by the progress alone. The weight might
        correspond to the length of the audio files for example.
        """
        raise NotImplementedError()

    def cancel(self):
        """Cancel the execution of the task."""
        raise NotImplementedError()

    def pause(self):
        """Pause the execution of the task."""
        raise NotImplementedError()

    def resume(self):
        """Resume the execution of the task after pausing."""
        raise NotImplementedError()

    def run(self):
        """Run the task."""
        raise NotImplementedError()

    def done(self):
        """Emit a "done" event."""
        self.emit("done")


GObject.signal_new("done", Task, GObject.SignalFlags.RUN_FIRST, None, [])
