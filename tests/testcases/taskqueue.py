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


class SyncSleepTask(Task):
    """Task that does nothing."""
    def __init__(self):
        super().__init__()

    def progress(self):
        """Fraction of how much of the task is completed."""
        # very useless example
        return 0

    def cancel(self):
        """Stop execution of the task."""
        pass

    def run(self):
        """Run the task"""
        time.sleep(0.1)
        self.callback()


class AsyncSleepTask(Task):
    """Task that does nothing as well, but this time asynchronously."""
    def __init__(self):
        self.progress = 0
        super().__init__()

    def progress(self):
        """Fraction of how much of the task is completed."""
        return self.progress

    def cancel(self):
        """Stop execution of the task."""
        pass

    def async_stuff(self, bus):
        """Sleep for some time and emit an event for GLib."""
        time.sleep(0.1)
        self.progress = 0.33
        time.sleep(0.1)
        self.progress = 0.67
        time.sleep(0.1)
        self.progress = 1

        # GLib has an event loop (possibly very similar to the one in node.js)
        # which, from my uneducated perspective, looks like it calls the
        # functions of idle_add and bus.connect as soon as it can during some
        # gtk main iterations.
        # Trigger calling done during the next gtk iterations:

        # this is also what gstreamer pipelines emit when they are done
        msg_type = Gst.MessageType(Gst.MessageType.EOS)
        msg = Gst.Message.new_custom(msg_type, None, None)
        bus.post(msg)

    def done(self, bus, message):
        """Write down that it is finished and call the callback."""
        self.running = False
        self.callback()

    def run(self):
        """Run the task"""
        bus = Gst.Bus()
        bus.connect('message', self.done)
        bus.add_signal_watch()
        thread = threading.Thread(target=self.async_stuff, args=(bus,))
        thread.run()


class SyncSleepTaskTest(unittest.TestCase):
    def test(self):
        """Checks if basic Task class functions are working properly."""
        task = SyncSleepTask()
        done = Mock()
        task.set_callback(done)
        task.run()
        done.assert_called_with(task)


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
        context.iteration(True)
        
        self.assertEqual(q.done, 1)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 0)

    def test_queue_multiple_async(self):
        """Example that is closer to the real world."""
        num_tasks = 5
        num_jobs = 2

        settings['forced-jobs'] = num_jobs
        q = TaskQueue()

        for i in range(num_tasks):
            q.add(AsyncSleepTask())
            self.assertEqual(q.done, 0)
            self.assertEqual(q.pending.qsize(), i + 1)
            self.assertEqual(len(q.running), 0)

        self.assertEqual(q.pending.qsize(), num_tasks)

        q.run()
        self.assertEqual(q.done, 0)
        # simultaneously running tasks are limited:
        self.assertEqual(q.pending.qsize(), num_tasks - num_jobs)
        self.assertEqual(len(q.running), num_jobs)

        # in the ui, some gtk iterations are performed to keep the ui
        # responsive while waiting for all tasks to finish.
        loop = GLib.MainLoop()
        context = loop.get_context()
        # call functions that are added to the event loop
        while q.done < num_tasks:
            # since only two tasks can be done at a time, after an iteration
            # new tasks are put into running state. So iteration has to be
            # called multiple times
            context.iteration(True)
        
        self.assertEqual(q.done, num_tasks)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 0)

    def test_queue_multiple_mixed(self):
        """Contains both synchronous and asynchronous tasks."""
        settings['forced-jobs'] = 2
        q = TaskQueue()

        q.add(AsyncSleepTask()) # a
        q.add(SyncSleepTask()) # b
        q.add(AsyncSleepTask()) # c
        q.add(SyncSleepTask()) # d
        q.add(AsyncSleepTask()) # e

        self.assertEqual(q.pending.qsize(), 5)

        loop = GLib.MainLoop()
        context = loop.get_context()

        q.run()

        # since b finishes synchronously, it already is done after .run()
        # so 3 tasks are removed from the queue already
        self.assertEqual(q.pending.qsize(), 2)
        self.assertEqual(q.done, 1)
        self.assertEqual(len(q.running), 2) # two async tasks, a and c

        # get the finish message from the running async tasks a and c now
        context.iteration(True)
        # d and e are added to the queue, d finishes immediately
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(q.done, 4)
        self.assertEqual(len(q.running), 1)

        # get message from e
        context.iteration(True)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(q.done, 5)
        self.assertEqual(len(q.running), 0)

    def test_pause(self):
        raise NotImplementedError('TODO')

    def test_cancel(self):
        raise NotImplementedError('TODO')


if __name__ == "__main__":
    unittest.main()
