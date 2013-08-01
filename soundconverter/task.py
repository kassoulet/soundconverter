#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2012 Gautier Portet
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
import gobject


class BackgroundTask:

    """A background task.

    To use: derive a subclass and define the methods started, and
    finished. Then call the start() method when you want to start the task.
    You must call done() when the processing is finished.
    Call the abort() method if you want to stop the task before it finishes
    normally."""

    def __init__(self):
        self.running = False
        self.listeners = {}
        self.progress = None

    def start(self):
        """Start running the task. Call started()."""
        self.emit('started')
        self.running = True
        self.run_start_time = time.time()

    def add_listener(self, signal, listener):
        """Add a custom listener to the given signal.
        Signals are 'started' and 'finished'"""
        if signal not in self.listeners:
            self.listeners[signal] = []
        self.listeners[signal].append(listener)

    def emit(self, signal):
        """Call the signal handlers.
        Callbacks are called as gtk idle funcs to be sure
        they are in the main thread."""
        gobject.idle_add(getattr(self, signal))
        if signal in self.listeners:
            for listener in self.listeners[signal]:
                gobject.idle_add(listener, self)

    def emit_sync(self, signal):
        """Call the signal handlers.
        Callbacks are called synchronously."""
        getattr(self, signal)()
        if signal in self.listeners:
            print(self.listeners[signal])
            for listener in self.listeners[signal]:
                listener(self)

    def done(self):
        """Call to end normally the task."""
        self.run_finish_time = time.time()
        if self.running:
            self.emit_sync('finished')
            self.running = False

    def abort(self):
        """Stop task processing. finished() is not called."""
        self.emit('aborted')
        self.running = False

    def aborted(self):
        """Called when the task is aborted."""
        pass

    def started(self):
        """Called when the task starts."""
        pass

    def finished(self):
        """Clean up the task after all work has been done."""
        pass
