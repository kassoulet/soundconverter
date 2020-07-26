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
import unittest
import threading
from unittest.mock import Mock
from gi.repository import GLib, Gst

from soundconverter.audio.taskqueue import TaskQueue
from soundconverter.audio.task import Task
from soundconverter.util.settings import settings
from util import reset_settings


class AsyncSleepTaskTest(unittest.TestCase):
    """Checks if async Task class functions are working properly."""
    def test_pause_resume(self):
        loop = GLib.MainLoop()
        context = loop.get_context()

        task = AsyncSleepTask()
        done = Mock()
        task.set_callback(done)

        task.run()
        time.sleep(0.3)
        context.iteration(False)
        done.assert_not_called()

        task.pause()
        time.sleep(0.3)
        context.iteration(False)
        done.assert_not_called()

        task.resume()
        time.sleep(0.3)
        context.iteration(False)
        done.assert_called_with(task)

    def test_cancel_run(self):
        loop = GLib.MainLoop()
        context = loop.get_context()

        task = AsyncSleepTask()
        done = Mock()
        task.set_callback(done)

        task.run()
        time.sleep(0.3)
        context.iteration(False)
        done.assert_not_called()

        task.cancel()
        done.assert_not_called()
        
        time.sleep(0.3)
        context.iteration(False)
        done.assert_not_called()

        task.run()
        done.assert_not_called()

        time.sleep(0.3)
        context.iteration(False)
        done.assert_not_called()

        time.sleep(0.3)
        context.iteration(False)
        done.assert_called_with(task)


if __name__ == "__main__":
    unittest.main()
