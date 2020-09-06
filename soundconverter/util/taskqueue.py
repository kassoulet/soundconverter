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
        self.all_tasks = []
        self.pending = Queue()
        self.running = []
        self.done = []
        self.finished = False
        self.paused = False

        self._timer = Timer()
        self._remaining_history = History(size=31)
        # In my experience the factor for the remaining time correction
        # is around 1.3. Start with it and then correct it if needed.
        self._smooth_remaining_time = Smoothing(factor=50, first_value=1.3)

    def add(self, task):
        """Add a task to the queue that will be executed later.

        Parameters
        ----------
        task : Task
            Any object inheriting from Task
        """
        task.set_callback(self.task_done)
        task.timer = Timer()
        self.all_tasks.append(task)
        self.pending.put(task)

    def get_progress(self, only_running=False):
        """Get the fraction of tasks that have been completed.

        returns a tuple of (total progress, task progress)
        with "task progress" being a list of (task, progress) tuples.
        """
        # some tasks may take longer, in order to communicate that they
        # provide a weight attribute.
        if len(self.all_tasks) == 0:
            return None
        total_weight = 0
        total_processed_weight = 0
        tasks = self.running if only_running else self.all_tasks

        task_progress = []

        for task in tasks:
            progress, weight = task.get_progress()
            total_processed_weight += progress * weight
            total_weight += weight
            task_progress.append((task, progress))

        return total_processed_weight / total_weight, task_progress

    def pause(self):
        """Pause all tasks."""
        self._timer.pause()
        self.paused = True
        for task in self.running:
            task.timer.pause()
            task.pause()

    def resume(self):
        """Resume all tasks after the queue has been paused."""
        self._timer.resume()
        for task in self.running:
            task.timer.resume()
            task.resume()
        self.paused = False

    def cancel(self):
        """Stop all tasks."""
        for task in self.running:
            # by calling run it can be resumed, but cancelled tasks will start
            # from the beginning. The proper way would be to call pause and
            # resume for such a functionality though.
            self.pending.put(task)
            task.timer.stop()
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
        task.timer.stop()
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
            task.timer.start()
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

    def get_remaining(self):
        """Calculate how many seconds are left until the queue is done."""
        if len(self.running) == 0:
            # cannot be estimated yet
            return None

        # replicate how the workload is distributed among the processes
        # to figure out how much time is remaining. This is needed because
        # at the end some processes will be idle while other are still
        # converting.
        workloads = [0] * get_num_jobs()

        total_processed_weight = 0
        total_duration = 0

        for task in self.all_tasks:
            if task.done:
                continue
            progress, weight = task.get_progress()
            smallest_index = 0
            smallest_workload = float('inf')
            for i, workload in enumerate(workloads):
                if workload < smallest_workload:
                    smallest_index = i
                    smallest_workload = workload
            remaining_weight = (1 - progress) * weight
            workloads[smallest_index] += remaining_weight

        for task in self.all_tasks:
            progress, weight = task.get_progress()
            total_duration += task.timer.get_duration()
            total_processed_weight += progress * weight

        if len(self.running) == get_num_jobs():
            # if possible, use the the taskqueues duration instead of the
            # sum of all tasks to account for overheads between running tasks
            taskqueue_duration = self.get_duration() * get_num_jobs()
            speed = total_processed_weight / taskqueue_duration
        else:
            speed = total_processed_weight / total_duration

        remaining = max(workloads) / speed

        # correct the remaining time based on how long it has actually
        # been running
        self._remaining_history.push({
            'time': time.time(),
            'remaining': remaining
        })
        historic = self._remaining_history.get_oldest()
        if historic is not None:
            seconds_since = time.time() - historic['time']
            remaining_change = historic['remaining'] - remaining
            if remaining_change > 0:
                factor = seconds_since / remaining_change
                # put some trust into the unfactored prediction after all.
                # sometimes for large files, the speed seems to decrease over
                # time, in which case the remaining_change is close to 0.
                # Don't make the factor super large then.
                factor = max(0.8, min(1.6, factor))
            else:
                factor = 1.6
            factor = self._smooth_remaining_time.smooth(factor)
            remaining = remaining * factor

        return remaining


class Smoothing:
    """Exponential smoothing for a single value."""
    def __init__(self, factor, first_value=None):
        self.factor = factor
        self.value = first_value

    def smooth(self, value):
        if self.value is not None:
            value = (self.value * self.factor + value) / (self.factor + 1)
        self.value = value
        return value


class History:
    """History of predictions."""
    def __init__(self, size):
        """Create a new History object, with a memory of `size`."""
        self.index = 0
        self.values = [None] * size

    def push(self, value):
        """Add a new value to the history, possibly overwriting old values."""
        self.values[self.index] = value
        self.index = (self.index + 1) % len(self.values)

    def get(self, offset):
        """Get a value offset steps in the past."""
        if offset >= len(self.values):
            # Doesn't carry such old values
            return None

        index = (self.index - offset) % len(self.values) - 1
        return self.values[index]

    def get_oldest(self):
        """Get the oldest known value."""
        index = len(self.values) - 1
        while index > 0:
            if self.get(index) is None:
                index -= 1
            else:
                break
        return self.get(index)


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
