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

import datetime
from queue import Queue

from soundconverter.util.settings import settings


class TaskQueue:
    """Executes multiple tasks in parallel."""
    # for now sequential
    def __init__(self):
        self.pending = Queue()
        self.running = []
        self.done = []
        self.duration_processed = 0
        self.overwrite_action = None

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

    def get_num_jobs(self):
        """Return the number of jobs that should be run in parallel."""
        return (
            settings['forced-jobs'] or
            settings['jobs'] or
            settings['cpu-count']
        )

    def task_done(self, task):
        """One task is done, start another one.

        query : dict
            the sample has to match


        This callback has to be called by the task, when the task is done.

        Parameters
        ----------
            task : Task
                A completed task
        """
        self.done.append(task)
        self.running.remove(task)
        if self.pending.qsize() > 0:
            self.start_next()
        else:
            # all tasks done done
            if self.running_tasks:
                raise RuntimeError
                
            self.window.set_sensitive()
            self.window.conversion_ended()

            total_time = self.run_finish_time - self.run_start_time
            total_time_format = str(datetime.timedelta(seconds=total_time))
            msg = _('Tasks done in %s') % total_time_format

            errors = [
                task.error for error in self.done
                if task.error is not None
            ]
            if len(errors) > 0:
                msg += ', {} error(s)'.format(len(errors))

            self.window.set_status(msg)
            if not self.window.is_active():
                notification(msg)

            self.reset_counters()

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
        jobs = self.get_num_jobs()
        while self.pending.qsize() > 0 and len(self.running) < jobs:
            self.start_next()
