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
        self.on_queue_finished = None
        self.run_start_time = None

        # state
        self.pending = Queue()
        self.running = []
        self.done = []
        self.duration_processed = 0

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
        return (running_progress + len(self.done)) / num_tasks

    def pause(self):
        """Pause all tasks."""
        for task in self.running:
            task.pause()

    def resume(self):
        """Resume all tasks after the queue has been paused."""
        for task in self.running:
            task.resume()

    def cancel(self):
        """Stop all tasks."""
        for task in self.running:
            # by calling run it can be resumed, but cancelled tasks will start
            # from the beginning. The proper way would be to call pause and
            # resume for such a functionality though.
            self.pending.put(task)
            task.cancel()

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
            # TODO add all of this to a callback (on_queue_finished) added in ui:
            # all tasks done done

            """self.window.set_sensitive()
            self.window.conversion_ended()

            total_time = time.time() - self.run_start_time
            total_time_format = str(datetime.timedelta(seconds=total_time))
            msg = _('Tasks done in %s') % total_time_format

            errors = [
                task.error for task in self.done
                if task.error is not None
            ]
            if len(errors) > 0:
                msg += ', {} error(s)'.format(len(errors))

            self.window.set_status(msg)
            if not self.window.is_active():
                notification(msg)"""

            if self.on_queue_finished is not None:
                self.on_queue_finished(self)

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
        self.run_start_time = time.time()
        num_jobs = get_num_jobs()
        while self.pending.qsize() > 0 and len(self.running) < num_jobs:
            self.start_next()

    def set_on_task_done(self, on_queue_finished):
        """Add a custom function to be used when the queue finishes."""
        self.on_queue_finished = on_queue_finished
