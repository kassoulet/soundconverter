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


class ConverterTest(unittest.TestCase):
    def setUp(self):
        self.num_tasks = 5
        self.num_jobs = 2
        settings['forced-jobs'] = self.num_jobs
        q = TaskQueue()
        for i in range(self.num_tasks):
            q.add(AsyncSleepTask())
            self.assertEqual(q.done, 0)
            self.assertEqual(q.pending.qsize(), i + 1)
            self.assertEqual(len(q.running), 0)
        self.assertEqual(q.pending.qsize(), self.num_tasks)
        self.q = q
        
    def tearDown(self):
        self.q = None

    def test_queue_multiple_async(self):
        self.q.run()
        self.assertEqual(self.q.done, 0)
        # simultaneously running tasks are limited:
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # in the ui, some gtk iterations are performed to keep the ui
        # responsive while waiting for all tasks to finish.
        loop = GLib.MainLoop()
        context = loop.get_context()
        # call functions that are added to the event loop
        while self.q.done < self.num_tasks:
            # since only two tasks can be done at a time, after an iteration
            # new tasks are put into running state. So iteration has to be
            # called multiple times
            context.iteration(True)

        self.assertEqual(self.q.done, self.num_tasks)
        self.assertEqual(self.q.pending.qsize(), 0)
        self.assertEqual(len(self.q.running), 0)

    def test_pause_resume(self):
        self.q.run()
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        self.q.pause()
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # after some time and running all accumulated glib events and stuff,
        # no job should be finished due to them being paused
        time.sleep(0.6)
        loop = GLib.MainLoop()
        context = loop.get_context()
        context.iteration(False)

        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        self.q.resume()
        # even after resuming, time has to pass
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # wait until the queue is completely done
        while self.q.done < self.num_tasks:
            # this blocks until bus.post(msg) is called:
            context.iteration(True)

        self.assertEqual(self.q.done, self.num_tasks)
        self.assertEqual(self.q.pending.qsize(), 0)
        self.assertEqual(len(self.q.running), 0)

    def test_cancel_run(self):
        self.assertEqual(self.q.done, 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks)
        self.assertEqual(len(self.q.running), 0)

        self.q.run()
        self.assertEqual(self.q.done, 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        self.q.cancel()
        self.assertEqual(self.q.done, 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks)
        self.assertEqual(len(self.q.running), 0)

        # after some time and running all accumulated glib events and stuff,
        # no job should be finished due to them being not running anymore.
        time.sleep(0.6)
        loop = GLib.MainLoop()
        context = loop.get_context()
        context.iteration(False)

        self.assertEqual(self.q.done, 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks)
        self.assertEqual(len(self.q.running), 0)

        self.q.run()
        # even after resuming, time has to pass
        self.assertEqual(self.q.done, 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # wait until the queue is completely done
        while self.q.done < self.num_tasks:
            # this blocks until bus.post(msg) is called:
            context.iteration(True)

        self.assertEqual(self.q.done, self.num_tasks)
        self.assertEqual(self.q.pending.qsize(), 0)
        self.assertEqual(len(self.q.running), 0)


class TaskQueueTest(unittest.TestCase):
    def tearDown(self):
        reset_settings()

    def test_queue_single(self):
        """A TaskQueue only consisting of synchronous tasks."""
        settings['forced-jobs'] = 1
        q = TaskQueue()

        q.add(SyncSleepTask())
        self.assertEqual(q.pending.qsize(), 1)
        self.assertEqual(len(q.running), 0)

        q.add(SyncSleepTask())
        self.assertEqual(q.pending.qsize(), 2)
        self.assertEqual(len(q.running), 0)

        q.run()
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 0)

    def test_queue_single_async(self):
        settings['forced-jobs'] = 1
        q = TaskQueue()

        q.add(AsyncSleepTask())
        self.assertEqual(q.done, 0)
        self.assertEqual(q.pending.qsize(), 1)
        self.assertEqual(len(q.running), 0)

        q.run()
        self.assertEqual(q.done, 0)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 1)

        # in the ui, some gtk iterations are performed to keep the ui
        # responsive while waiting for all tasks to finish.
        loop = GLib.MainLoop()
        context = loop.get_context()
        # call functions that are added to the event loop. In this case,
        # the listeners for messages from our AsyncSleepTask
        # wait until the queue is completely done
        while q.done < 1:
            # this blocks until bus.post(msg) is called:
            context.iteration(True)

        self.assertEqual(q.done, 1)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 0)


if __name__ == "__main__":
    unittest.main()
