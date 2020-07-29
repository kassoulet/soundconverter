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

# pylint: skip-file

import os
import sys
from urllib.parse import urlparse
from gettext import gettext as _
import traceback

from gi.repository import Gst, Gtk, GLib, GObject, Gio

from soundconverter.util.fileoperations import vfs_encode_filename, unquote_filename, vfs_unlink, vfs_rename, \
    vfs_exists, beautify_uri
from soundconverter.util.task import BackgroundTask
from soundconverter.util.queue import TaskQueue
from soundconverter.util.logger import logger
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.formats import mime_whitelist, filename_blacklist
from soundconverter.util.error import show_error

try:
    from soundconverter.notify import notification
except Exception:
    def notification(msg):
        pass

from fnmatch import fnmatch

import time


def gtk_iteration():
    while Gtk.events_pending():
        Gtk.main_iteration(False)


def gtk_sleep(duration):
    start = time.time()
    while time.time() < start + duration:
        time.sleep(0.010)
        gtk_iteration()


required_elements = ('decodebin', 'fakesink', 'audioconvert', 'typefind', 'audiorate')
for element in required_elements:
    if not Gst.ElementFactory.find(element):
        logger.info(("required gstreamer element \'%s\' not found." % element))
        sys.exit(1)

gstreamer_source = 'giosrc'
gstreamer_sink = 'giosink'
encode_filename = vfs_encode_filename

# used to dismiss codec installation if the user already canceled it
user_canceled_codec_installation = False


class Pipeline(BackgroundTask):
    """A background task for running a GstPipeline."""

    def __init__(self):
        BackgroundTask.__init__(self)
        self.pipeline = None
        self.sound_file = None
        self.command = []
        self.parsed = False
        self.signals = []
        self.processing = False
        self.eos = False
        self.error = None
        self.connected_signals = []

    def started(self):
        self.play()

    def cleanup(self):
        for element, sid in self.connected_signals:
            element.disconnect(sid)
        self.connected_signals = []
        self.stop_pipeline()

    def aborted(self):
        self.cleanup()

    def finished(self):
        self.cleanup()

    def add_command(self, command):
        self.command.append(command)

    def add_signal(self, name, signal, callback):
        self.signals.append((name, signal, callback,))

    def found_tag(self, decoder, something, taglist):
        pass

    def restart(self):
        self.parsed = False
        self.duration = None
        self.finished()
        if vfs_exists(self.output_filename):
            vfs_unlink(self.output_filename)
        self.play()

    def install_plugin_cb(self, result):
        return

    def on_error(self, error):
        self.error = error
        logger.error('{} ({})'.format(error, ' ! '.join(self.command)))

    def on_message_(self, bus, message):
        self.on_message_(bus, message)
        return True

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            error, __ = message.parse_error()
            self.eos = True
            self.error = error
            self.on_error(error)
            self.done()
        elif t == Gst.MessageType.EOS:
            print('Gst.MessageType.EOS')
            self.eos = True
            self.done()
        elif t == Gst.MessageType.TAG:
            self.found_tag(self, '', message.parse_tag())
        return True

    def stop_pipeline(self):
        if not self.pipeline:
            logger.debug('pipeline already stopped!')
            return
        self.pipeline.set_state(Gst.State.NULL)
        bus = self.pipeline.get_bus()
        bus.disconnect(self.watch_id)
        bus.remove_signal_watch()
        self.pipeline = None

    def get_position(self):
        return NotImplementedError

    def query_duration(self):
        """Ask for the duration of the current pipeline."""
        try:
            if not self.sound_file.duration and self.pipeline:
                self.sound_file.duration = self.pipeline.query_duration(Gst.Format.TIME)[1] / Gst.SECOND
                if self.sound_file.duration <= 0:
                    self.sound_file.duration = None
        except Gst.QueryError:
            self.sound_file.duration = None


class TypeFinder(Pipeline):
    def __init__(self, sound_file, silent=False):
        Pipeline.__init__(self)
        self.sound_file = sound_file

        command = '{} location="{}" ! decodebin name=decoder ! fakesink'.format(
            gstreamer_source, encode_filename(self.sound_file.uri)
        )
        self.add_command(command)
        self.add_signal('decoder', 'pad-added', self.pad_added)
        # 'typefind' is the name of the typefind element created inside
        # decodebin. we can't use our own typefind before decodebin anymore,
        # since its caps would've been the same as decodebin's sink caps.
        self.add_signal('typefind', 'have-type', self.have_type)
        self.silent = silent

    def log(self, msg):
        """Print a line to the console, but only when the TypeFinder itself is not set to silent.

        It can also be disabled with the -q command line option.
        """
        if not self.silent:
            logger.info(msg)

    def on_error(self, error):
        self.error = error
        self.log('ignored-error: {} ({})'.format(error, ' ! '.join(self.command)))

    def set_found_type_hook(self, found_type_hook):
        self.found_type_hook = found_type_hook

    def pad_added(self, decoder, pad):
        """Called when a decoded pad is created."""
        self.query_duration()
        self.done()

    def have_type(self, typefind, probability, caps):
        mime_type = caps.to_string()
        logger.debug('have_type: {} {}'.format(mime_type, self.sound_file.filename_for_display))
        self.sound_file.mime_type = None
        for t in mime_whitelist:
            if t in mime_type:
                self.sound_file.mime_type = mime_type
        if not self.sound_file.mime_type:
            self.log('mime type skipped: {}'.format(mime_type))
        for t in filename_blacklist:
            if fnmatch(self.sound_file.uri, t):
                self.sound_file.mime_type = None
                self.log('filename blacklisted ({}): {}'.format(t, self.sound_file.filename_for_display))

        return True

    def finished(self):
        Pipeline.finished(self)
        if self.error:
            return
        if self.found_type_hook and self.sound_file.mime_type:
            self.found_type_hook(self.sound_file, self.sound_file.mime_type)
            self.sound_file.mime_type = True


class Decoder(Pipeline):
    """A GstPipeline background task that decodes data and finds tags."""
    def have_type(self, typefind, probability, caps):
        pass

    def pad_added(self, decoder, pad):
        """Called when a decoded pad is created."""
        self.processing = True
        self.query_duration()

    def finished(self):
        Pipeline.finished(self)

    def get_sound_file(self):
        return self.sound_file

    def get_input_uri(self):
        return self.sound_file.uri

    def get_position(self):
        """Return the current pipeline position in the stream."""
        self.query_position()
        return self.position


class TagReader(Decoder):
    """A GstPipeline background task for finding meta tags in a file."""

    def __init__(self, sound_file):
        Decoder.__init__(self, sound_file)
        self.found_tag_hook = None
        self.found_tags = False
        self.tagread = False
        self.run_start_time = 0
        self.add_command('fakesink')
        self.add_signal(None, 'message::state-changed', self.on_state_changed)
        self.tagread = False

    def set_found_tag_hook(self, found_tag_hook):
        self.found_tag_hook = found_tag_hook

    def on_state_changed(self, bus, message):
        new = message.parse_state_changed()
        if new == Gst.State.PLAYING and not self.tagread:
            self.tagread = True
            logger.debug('TagReading done…')
            self.done()

    def finished(self):
        Pipeline.finished(self)
        self.sound_file.tags_read = True
        if self.found_tag_hook:
            GLib.idle_add(self.found_tag_hook, self)

class ConverterQueue(TaskQueue):
    """Background task for converting many files."""

    def __init__(self, window):
        TaskQueue.__init__(self)
        self.window = window
        self.overwrite_action = None
        self.reset_counters()

    def add(self, sound_file):
        # generate a temporary filename from source name and output suffix
        output_filename = self.window.prefs.generate_temp_filename(sound_file)

        if vfs_exists(output_filename):
            # always overwrite temporary files
            vfs_unlink(output_filename)

        path = urlparse(output_filename)[2]
        path = unquote_filename(path)

        gio_settings = get_gio_settings()

        c = Converter(
            sound_file, output_filename,
            gio_settings.get_string('output-mime-type'),
            gio_settings.get_boolean('delete-original'),
            gio_settings.get_boolean('output-resample'),
            gio_settings.get_int('resample-rate'),
            gio_settings.get_boolean('force-mono'),
        )

        c.init()
        c.add_listener('finished', self.on_task_finished)
        self.add_task(c)

    def abort(self):
        TaskQueue.abort(self)
        self.window.set_sensitive()
        self.reset_counters()

    def start(self):
        # self.waiting_tasks.sort(key=Converter.get_duration, reverse=True)
        TaskQueue.start(self)
