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
from queue import Queue

from soundconverter.util.settings import get_num_jobs
from soundconverter.util.logger import logger


class TaskQueue:
    """Executes multiple tasks in parallel."""
    def __init__(self):
        self._on_queue_finished = None

        # state
        self.pending = Queue()
        self.running = []
        self.done = []
        self.finished = False
        self.paused = False
        self._timer = Timer()

    def add(self, task):
        """Add a task to the queue that will be executed later.

        Parameters
        ----------
        task : Task
            Any object inheriting from Task
        """
        task.set_callback(self.task_done)
        self.pending.put(task)

    def get_progress(self):
        """Get the fraction of tasks that have been completed."""
        running_progress = sum(task.get_progress() for task in self.running)
        num_tasks = len(self.done) + len(self.running) + self.pending.qsize()
        if num_tasks == 0:
            return None
        return (running_progress + len(self.done)) / num_tasks

    def pause(self):
        """Pause all tasks."""
        self._timer.pause()
        self.paused = True
        for task in self.running:
            task.pause()

    def resume(self):
        """Resume all tasks after the queue has been paused."""
        self._timer.resume()
        for task in self.running:
            task.resume()
        self.paused = False

    def cancel(self):
        """Stop all tasks."""
        for task in self.running:
            # by calling run it can be resumed, but cancelled tasks will start
            # from the beginning. The proper way would be to call pause and
            # resume for such a functionality though.
            self.pending.put(task)
            task.cancel()
        self._timer.reset()
        self.running = []

    def task_done(self, task):
        """One task is done, start another one.

        This callback has to be called by the task, when the task is done.

        Parameters
        ----------
        task : Task
            A completed task
        """
        self.done.append(task)
        if task not in self.running:
            logger.warning('tried to remove task that was already removed')
        else:
            self.running.remove(task)
        if self.pending.qsize() > 0:
            self.start_next()
        elif len(self.running) == 0:
            self.finished = True
            self._timer.stop()
            if self._on_queue_finished is not None:
                self._on_queue_finished(self)

    def start_next(self):
        """Start the next task if available."""
        if self.pending.qsize() > 0:
            task = self.pending.get()
            self.running.append(task)
            task.run()

    def run(self):
        """Run as many tasks as the configured number of jobs.
        
        Finished tasks will trigger running the next task over the task_done
        callback.
        """
        self._timer.start()
        num_jobs = get_num_jobs()
        while self.pending.qsize() > 0 and len(self.running) < num_jobs:
            self.start_next()

    def set_on_queue_finished(self, on_queue_finished):
        """Add a custom function to be used when the queue finishes."""
        self._on_queue_finished = on_queue_finished

    def get_duration(self):
        """Get for how many seconds the queue has been actively running.

        The time spent while being paused is not included.
        """
        return self._timer.get_duration()


class Timer:
    """Time how long the TaskQueue took."""
    # separate class because I would like to not pollute the TaskQueue
    # with a bunch of timing variables
    def __init__(self):
        self.reset()

    def reset(self):
        self.run_start_time = None
        self.pause_duration = 0
        self.pause_time = None
        self.finished_time = None

    def stop(self):
        self.finished_time = time.time()

    def start(self):
        self.run_start_time = time.time()

    def pause(self):
        self.pause_time = time.time()

    def resume(self):
        self.pause_duration += time.time() - self.pause_time
        self.pause_time = None

    def get_duration(self):
        """Get for how many seconds the queue has been actively running.

        The time spent while being paused is not included.
        """
        if self.run_start_time is None:
            return 0
        if self.pause_time is not None:
            # still being paused
            pause_duration = time.time() - self.pause_time
        else:
            pause_duration = self.pause_duration
        if self.finished_time is None:
            # still running
            finished_time = time.time()
        else:
            finished_time = self.finished_time
        return finished_time - self.run_start_time - pause_duration
