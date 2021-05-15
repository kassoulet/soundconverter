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

from fnmatch import fnmatch
from threading import Thread

from gi.repository import Gst, GObject, GstPbutils, GLib

from soundconverter.util.task import Task
from soundconverter.util.logger import logger
from soundconverter.util.settings import get_num_jobs
from soundconverter.util.formats import filename_denylist

type_getters = {
    GObject.TYPE_STRING: 'get_string',
    GObject.TYPE_DOUBLE: 'get_double',
    GObject.TYPE_FLOAT: 'get_float',
    GObject.TYPE_INT: 'get_int',
    GObject.TYPE_UINT: 'get_uint',
}


def add_discoverers(task_queue, sound_files):
    """Fill a TaskQueue with Discoverer tasks for optimized discovery."""
    chunk = []
    chunksize = len(sound_files) / get_num_jobs()
    for sound_file in sound_files:
        chunk.append(sound_file)
        if len(chunk) >= chunksize or sound_file is sound_files[-1]:
            discoverer = Discoverer(chunk)
            task_queue.add(discoverer)
            chunk = []

    if len(chunk) > 0:
        raise AssertionError(
            'All chunks should have been added to discoverers'
        )


def get_sound_files(task_queue):
    """Get all SoundFiles of discoverer tasks in a TaskQueue"""
    sound_files = []
    for task in task_queue:
        if isinstance(task, Discoverer):
            for sound_file in task.sound_files:
                sound_files.append(sound_file)
    return sound_files


def is_denylisted(sound_file):
    """Check the file against the denylist."""
    for file_pattern in filename_denylist:
        if fnmatch(sound_file.uri, file_pattern):
            return file_pattern
    return False


class DiscovererThread(Thread):
    """Discover if multiple SoundFiles can be read and their tags."""

    # This is the fastest way I could figure out. discover_uri_async
    # was not faster than discover_uri, and the UI only stayed responsive
    # as long as only 1 discover_uri_async job was running at a time.
    # Maybe it was a bit too much for the GLib event loop, who knows.
    # Running multiple discover_uri_async jobs at a time also didn't
    # improve the performance. By using threads with synchronous
    # discovery, I could get a very responsive UI while spawning 12
    # Threads with a drastic ~5-times performance increase for ~360
    # files.
    # I couldn't get it to work with the multiprocessing module though,
    # because the discover_uri function would hang.

    def __init__(self, sound_files, bus):
        super().__init__()
        self.sound_files = sound_files
        self.bus = bus

    def run(self):
        """Run the Thread."""
        for sound_file in self.sound_files:
            self._analyse_file(sound_file)

            msg_type = Gst.MessageType(Gst.MessageType.PROGRESS)
            msg = Gst.Message.new_custom(msg_type, None, None)
            self.bus.post(msg)

        msg_type = Gst.MessageType(Gst.MessageType.EOS)
        msg = Gst.Message.new_custom(msg_type, None, None)
        self.bus.post(msg)

    def _analyse_file(self, sound_file):
        """Figure out readable, tags and duration properties."""
        sound_file.readable = False
        denylisted_pattern = is_denylisted(sound_file)
        if denylisted_pattern:
            logger.info('filename denylisted ({}): {}'.format(
                denylisted_pattern, sound_file.filename_for_display
            ))
            return

        try:
            discoverer = GstPbutils.Discoverer()
            info = discoverer.discover_uri(sound_file.uri)

            # whatever anybody might ever need from it, here it is:
            sound_file.info = info

            taglist = info.get_tags()
            if not taglist: return
            taglist.foreach(lambda *args: self._add_tag(*args, sound_file))

            filename = sound_file.filename_for_display
            logger.debug('found tag: {}'.format(filename))
            for tag, value in sound_file.tags.items():
                logger.debug('    {}: {}'.format(tag, value))

            # since threads share memory, this doesn't have to be sent
            # over a bus or queue, but rather can be written into the
            # sound_file
            sound_file.readable = True
            sound_file.duration = info.get_duration() / Gst.SECOND
        except Exception as error:
            if not isinstance(error, GLib.Error):
                logger.error(str(error))

    def _add_tag(self, taglist, tag, sound_file):
        """Convert the taglist to a dict one by one."""
        # only really needed to construct output paths
        tag_type = Gst.tag_get_type(tag)

        if tag_type in type_getters:
            getter = getattr(taglist, type_getters[tag_type])
            value = str(getter(tag)[1])
            sound_file.tags[tag] = value

        if 'datetime' in tag:
            date_time = taglist.get_date_time(tag)[1]
            sound_file.tags['year'] = date_time.get_year()
            sound_file.tags['date'] = date_time.to_iso8601_string()[:10]


class Discoverer(Task):
    """Find type and tags of a SoundFile if possible."""

    def __init__(self, sound_files):
        """Find type and tags of a SoundFile if possible."""
        self.sound_files = sound_files
        self.error = None
        self.running = False
        self.callback = lambda: None
        self.discovered = 0
        self.queue = None

        self.bus = None
        self.thread = None

    def get_progress(self):
        """Fraction of how much of the task is completed."""
        return self.discovered / len(self.sound_files), 1

    def cancel(self):
        """Cancel execution of the task."""
        # fast task, use case doesn't exist
        self.callback()

    def pause(self):
        """Pause execution of the task."""
        # fast task, use case doesn't exist

    def resume(self):
        """Resume execution of the task."""
        # fast task, use case doesn't exist

    def run(self):
        self.running = True
        bus = Gst.Bus()
        bus.connect('message', self._on_message)
        bus.add_signal_watch()
        thread = DiscovererThread(self.sound_files, bus)
        thread.start()
        self.bus = bus
        self.thread = thread

    def _on_message(self, _, message):
        """Write down that it is finished and call the callback."""
        if message.type == Gst.MessageType.EOS:
            self.running = False
            self.callback()
        else:
            self.discovered += 1
