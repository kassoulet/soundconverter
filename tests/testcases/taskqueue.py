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
from soundconverter.util.settings import get_gio_settings
from util import reset_settings


class SyncSleepTask(Task):
    """Task that does nothing.
    
    Multiple of those tasks can't run in parallel.
    """
    def __init__(self):
        super().__init__()

    def progress(self):
        """Fraction of how much of the task is completed."""
        # it's blocking anyways, so progress cannot be asked for
        # until the end.
        return 1

    def cancel(self):
        pass

    def run(self):
        time.sleep(0.1)
        self.callback()

    def pause(self):
        # cannot be paused
        pass

    def resume(self):
        pass


class AsyncSleepTask(Task):
    """Task that does nothing as well, but this time asynchronously.
    
    Can run in parallel. This is just an example on how a Task might work.
    """
    def __init__(self):
        self.progress = 0
        self.paused = False
        self.cancelled = False
        self.resume_event = threading.Event()
        super().__init__()

    def progress(self):
        """Fraction of how much of the task is completed."""
        return self.progress

    def async_stuff(self, bus):
        """Sleep for some time and emit an event for GLib."""
        # sleep for a total of 0.5s, simulate some sort of task that can
        # be paused.
        while self.progress < 1:
            if self.paused:
                # wait for the resume event
                self.resume_event.wait()
                self.resume_event.clear()

            if self.cancelled:
                # don't post the msg, because that would indicate success
                return

            time.sleep(0.025)
            self.progress += 0.1

        # GLib has an event loop (possibly very similar to the one in node.js)
        # which, from my uneducated perspective, looks like it calls the
        # functions passed to idle_add and bus.connect as soon as it can
        # during some gtk main iterations.
        # Trigger calling done during the next gtk iterations:

        # this is also what gstreamer pipelines emit when they are done
        msg_type = Gst.MessageType(Gst.MessageType.EOS)
        msg = Gst.Message.new_custom(msg_type, None, None)
        bus.post(msg)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.resume_event.set()

    def cancel(self):
        self.cancelled = True
        self.progress = 0
        # make sure to not block cancelling because of the pause
        self.resume()

    def run(self):
        self.cancelled = False
        bus = Gst.Bus()
        bus.connect('message', self.done)
        bus.add_signal_watch()
        thread = threading.Thread(target=self.async_stuff, args=(bus,))
        thread.start()
        # don't do thread.join, because that would block the main thread

    def done(self, bus, message):
        """Write down that it is finished and call the callback."""
        self.running = False
        self.callback()


class SyncSleepTaskTest(unittest.TestCase):
    def test(self):
        """Checks if basic Task class functions are working properly."""
        task = SyncSleepTask()
        done = Mock()
        task.set_callback(done)
        task.run()
        done.assert_called_with(task)


class AsyncSleepTaskTest(unittest.TestCase):
    """Checks if async Task class functions are working properly."""
    def test_pause_resume(self):
        loop = GLib.MainLoop()
        context = loop.get_context()

        task = AsyncSleepTask()
        done = Mock()
        task.set_callback(done)

        task.run()
        time.sleep(0.15)
        context.iteration(False)
        done.assert_not_called()

        task.pause()
        time.sleep(0.15)
        context.iteration(False)
        done.assert_not_called()

        task.resume()
        time.sleep(0.15)
        context.iteration(False)
        done.assert_called_with(task)

    def test_cancel_run(self):
        loop = GLib.MainLoop()
        context = loop.get_context()

        task = AsyncSleepTask()
        done = Mock()
        task.set_callback(done)

        task.run()
        time.sleep(0.15)
        context.iteration(False)
        done.assert_not_called()

        task.cancel()
        done.assert_not_called()
        
        time.sleep(0.15)
        context.iteration(False)
        done.assert_not_called()

        task.run()
        done.assert_not_called()

        time.sleep(0.15)
        context.iteration(False)
        done.assert_not_called()

        time.sleep(0.15)
        context.iteration(False)
        done.assert_called_with(task)


class AsyncMulticoreTaskQueueTest(unittest.TestCase):
    """Example closest to the real world, should be tested well."""
    def setUp(self):
        get_gio_settings().set_boolean('limit-jobs', True)
        self.num_tasks = 5
        q = TaskQueue()
        for i in range(self.num_tasks):
            q.add(AsyncSleepTask())
            self.assertEqual(len(q.done), 0)
            self.assertEqual(q.pending.qsize(), i + 1)
            self.assertEqual(len(q.running), 0)
        self.assertEqual(q.pending.qsize(), self.num_tasks)
        self.q = q
        
    def tearDown(self):
        self.q = None

    def test_queue_multiple_async(self):
        self.num_jobs = 2
        get_gio_settings().set_int('number-of-jobs', self.num_jobs)

        self.q.run()
        self.assertEqual(len(self.q.done), 0)
        # simultaneously running tasks are limited:
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # in the ui, some gtk iterations are performed to keep the ui
        # responsive while waiting for all tasks to finish.
        loop = GLib.MainLoop()
        context = loop.get_context()
        # call functions that are added to the event loop
        while len(self.q.done) < self.num_tasks:
            # since only two tasks can be done at a time, after an iteration
            # new tasks are put into running state. So iteration has to be
            # called multiple times
            context.iteration(True)

        self.assertEqual(len(self.q.done), self.num_tasks)
        self.assertEqual(self.q.pending.qsize(), 0)
        self.assertEqual(len(self.q.running), 0)

    def test_pause_resume(self):
        self.num_jobs = 5
        get_gio_settings().set_int('number-of-jobs', self.num_jobs)

        self.q.run()
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        self.q.pause()
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # after some time and running all accumulated glib events and stuff,
        # no job should be finished due to them being paused
        time.sleep(0.3)
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
        while len(self.q.done) < self.num_tasks:
            # this blocks until bus.post(msg) is called:
            context.iteration(True)

        self.assertEqual(len(self.q.done), self.num_tasks)
        self.assertEqual(self.q.pending.qsize(), 0)
        self.assertEqual(len(self.q.running), 0)

    def test_cancel_run(self):
        self.num_jobs = 5
        get_gio_settings().set_int('number-of-jobs', self.num_jobs)
        
        loop = GLib.MainLoop()
        context = loop.get_context()

        self.assertEqual(len(self.q.done), 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks)
        self.assertEqual(len(self.q.running), 0)

        self.q.run()
        self.assertEqual(len(self.q.done), 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        time.sleep(0.15)
        context.iteration(False)

        self.q.cancel()
        self.assertEqual(len(self.q.done), 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks)
        self.assertEqual(len(self.q.running), 0)

        # after some time and running all accumulated glib events and stuff,
        # no job should be finished due to them not running anymore.
        time.sleep(0.3)
        context.iteration(False)

        self.assertEqual(len(self.q.done), 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks)
        self.assertEqual(len(self.q.running), 0)

        self.q.run()
        # even after resuming, time has to pass, but the previous progress of
        # 0.3 seconds should be reset.
        time.sleep(0.15)
        context.iteration(False)
        self.assertEqual(len(self.q.done), 0)
        self.assertEqual(self.q.pending.qsize(), self.num_tasks - self.num_jobs)
        self.assertEqual(len(self.q.running), self.num_jobs)

        # only after some more time all are done, but don't sleep longer
        # than 0.3 more seconds, because after 0.5s they should be done.
        slept = 0 
        while len(self.q.done) < self.num_tasks and slept < 0.15:
            time.sleep(0.05)
            slept += 0.05
            context.iteration(False)

        self.assertEqual(len(self.q.done), self.num_tasks)
        self.assertEqual(self.q.pending.qsize(), 0)
        self.assertEqual(len(self.q.running), 0)


class TaskQueueTest(unittest.TestCase):
    def tearDown(self):
        reset_settings()

    def test_queue_single(self):
        """A TaskQueue only consisting of synchronous tasks."""
        get_gio_settings().set_boolean('limit-jobs', True)
        get_gio_settings().set_int('number-of-jobs', 1)
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
        get_gio_settings().set_boolean('limit-jobs', True)
        get_gio_settings().set_int('number-of-jobs', 1)
        q = TaskQueue()

        q.add(AsyncSleepTask())
        self.assertEqual(len(q.done), 0)
        self.assertEqual(q.pending.qsize(), 1)
        self.assertEqual(len(q.running), 0)

        q.run()
        self.assertEqual(len(q.done), 0)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 1)

        # in the ui, some gtk iterations are performed to keep the ui
        # responsive while waiting for all tasks to finish.
        loop = GLib.MainLoop()
        context = loop.get_context()
        # call functions that are added to the event loop. In this case,
        # the listeners for messages from our AsyncSleepTask
        # wait until the queue is completely done
        while len(q.done) < 1:
            # this blocks until bus.post(msg) is called:
            context.iteration(True)

        self.assertEqual(len(q.done), 1)
        self.assertEqual(q.pending.qsize(), 0)
        self.assertEqual(len(q.running), 0)


if __name__ == "__main__":
    unittest.main()
