#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2017 Gautier Portet
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

import os
import sys
from urllib.parse import urlparse
from gettext import gettext as _
import traceback

from gi.repository import Gst, Gtk, GLib, GObject, Gio

from soundconverter.fileoperations import vfs_encode_filename, unquote_filename, vfs_unlink, vfs_rename, \
    vfs_exists, beautify_uri
from soundconverter.task import BackgroundTask
from soundconverter.queue import TaskQueue
from soundconverter.utils import logger, idle
from soundconverter.settings import get_gio_settings
from soundconverter.formats import mime_whitelist, filename_blacklist
from soundconverter.error import show_error

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


# load gstreamer audio profiles
_GCONF_PROFILE_PATH = "/system/gstreamer/1.0/audio/profiles/"
_GCONF_PROFILE_LIST_PATH = "/system/gstreamer/1.0/audio/global/profile_list"
audio_profiles_list = []
audio_profiles_dict = {}

try:
    import gi
    gi.require_version('GConf', '2.0')
    from gi.repository import GConf
    _GCONF = GConf.Client.get_default()
    profiles = _GCONF.all_dirs(_GCONF_PROFILE_LIST_PATH)
    for name in profiles:
        if _GCONF.get_bool(_GCONF_PROFILE_PATH + name + "/active"):
            # get profile
            description = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/name")
            extension = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/extension")
            pipeline = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/pipeline")
            # check profile validity
            if not extension or not pipeline:
                continue
            if not description:
                description = extension
            if description in audio_profiles_dict:
                continue
                # store
            profile = description, extension, pipeline
            audio_profiles_list.append(profile)
            audio_profiles_dict[description] = profile
except (ImportError, ValueError):
    pass

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

encoders = (
    ('flacenc', 'FLAC', 'flac-enc'),
    ('wavenc', 'WAV', 'wav-enc'),
    ('vorbisenc', 'Ogg Vorbis', 'vorbis-enc'),
    ('oggmux', 'Ogg Vorbis', 'vorbis-mux'),
    ('id3mux', 'MP3 tags', 'mp3-id-tags'),
    ('id3v2mux', 'MP3 tags', 'mp3-id-tags'),
    ('xingmux', 'VBR tags', 'mp3-vbr-tags'),
    ('lamemp3enc', 'MP3', 'mp3-enc'),
    ('faac', 'AAC', 'aac-enc'),
    ('avenc_aac', 'AAC', 'aac-enc'),
    ('mp4mux', 'AAC', 'aac-mux'),
    ('opusenc', 'Opus', 'opus-enc'),
)

available_elements = set()
functions = dict()

for encoder, name, function in encoders:
    have_it = bool(Gst.ElementFactory.find(encoder))
    if have_it:
        available_elements.add(encoder)
    else:
        logger.info('  {} gstreamer element not found'.format(encoder))
    function += '_' + name
    functions[function] = functions.get(function) or have_it

for function in sorted(functions):
    if not functions[function]:
        logger.info('  disabling {} output.'.format(function.split('_')[1]))

if 'oggmux' not in available_elements:
    available_elements.discard('vorbisenc')
if 'mp4mux' not in available_elements:
    available_elements.discard('faac')
    available_elements.discard('avenc_aac')


class Pipeline(BackgroundTask):
    """A background task for running a GstPipeline."""

    def __init__(self):
        BackgroundTask.__init__(self)
        self.pipeline = None
        self.sound_file = None
        self.command = ''
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

    def add_command(self, command, sep='!'):
        """A little helper to keep the code cleaner. Constructs a gstreamer pipeline, which is
        most of the time multiple plugins separated by exclamation marks."""
        if len(self.command) == 0:
            self.command += '{}'.format(command)
        else:
            self.command += ' {} {}'.format(sep, command)

    def add_signal(self, name, signal, callback):
        self.signals.append((name, signal, callback,))

    def toggle_pause(self, paused):
        if not self.pipeline:
            logger.debug('toggle_pause(): pipeline is None !')
            return

        if paused:
            self.pipeline.set_state(Gst.State.PAUSED)
        else:
            self.pipeline.set_state(Gst.State.PLAYING)

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
        return  # XXX
        if result in (Gst.pbutils.INSTALL_PLUGINS_SUCCESS,
                      Gst.pbutils.INSTALL_PLUGINS_PARTIAL_SUCCESS):
            Gst.update_registry()
            self.restart()
            return
        if result == Gst.pbutils.INSTALL_PLUGINS_USER_ABORT:
            self.error = _('Plugin installation aborted.')
            global user_canceled_codec_installation
            user_canceled_codec_installation = True
            self.done()
            return
        self.done()
        show_error('Error', 'failed to install plugins: {}'.format(GLib.markup_escape_text(str(result))))

    def on_error(self, error):
        self.error = error
        logger.error('{} ({})'.format(error, self.command))

    def on_message_(self, bus, message):
        self.on_message_(bus, message)
        return True

    # @idle
    def on_message(self, bus, message):
        import threading

        t = message.type
        if t == Gst.MessageType.ERROR:
            error, __ = message.parse_error()
            self.eos = True
            self.error = error
            self.on_error(error)
            self.done()
            """XXX elif Gst.pbutils.is_missing_plugin_message(message):
            global user_canceled_codec_installation
            detail = Gst.pbutils.missing_plugin_message_get_installer_detail(message)
            logger.debug('missing plugin: {} {}'.format(detail.split('|')[3], self.sound_file.uri))
            self.pipeline.set_state(Gst.State.NULL)
            if Gst.pbutils.install_plugins_installation_in_progress():
                while Gst.pbutils.install_plugins_installation_in_progress():
                    gtk_sleep(0.1)
                self.restart()
                return
            if user_canceled_codec_installation:
                self.error = 'Plugin installation cancelled'
                logger.debug(self.error)
                self.done()
                return
            ctx = Gst.pbutils.InstallPluginsContext()
            Gst.pbutils.install_plugins_async([detail], ctx, self.install_plugin_cb)
            """
        elif t == Gst.MessageType.EOS:
            self.eos = True
            self.done()
        elif t == Gst.MessageType.TAG:
            self.found_tag(self, '', message.parse_tag())
        return True

    def play(self):
        """Execute the gstreamer command"""
        if not self.parsed:
            logger.debug('launching: \'{}\''.format(self.command))
            try:
                # see https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html
                self.pipeline = Gst.parse_launch(self.command)
                bus = self.pipeline.get_bus()
                assert not self.connected_signals
                self.connected_signals = []
                for name, signal, callback in self.signals:
                    if name:
                        element = self.pipeline.get_by_name(name)
                    else:
                        element = bus
                    sid = element.connect(signal, callback)
                    self.connected_signals.append((element, sid,))

                self.parsed = True

            except GLib.GError as e:
                show_error('GStreamer error when creating pipeline', str(e))
                self.error = str(e)
                self.eos = True
                self.done()
                return

            bus.add_signal_watch()
            self.watch_id = bus.connect('message', self.on_message)

        self.pipeline.set_state(Gst.State.PLAYING)

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

        encoded_filename = encode_filename(self.sound_file.uri)
        self.add_command('{} location="{}"'.format(gstreamer_source, encoded_filename))
        self.add_command('decodebin name=decoder')
        self.add_command('fakesink')

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
        self.log('ignored-error: {} ({})'.format(error, self.command))

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

    def __init__(self, sound_file):
        Pipeline.__init__(self)
        self.sound_file = sound_file
        self.time = 0
        self.position = 0

        encoded_filename = encode_filename(self.sound_file.uri)
        self.add_command('{} location="{}" name=src'.format(gstreamer_source, encoded_filename))
        self.add_command('decodebin name=decoder')

        self.add_signal('decoder', 'pad-added', self.pad_added)

        # In order to possibly add more actions that should be performed along with writing
        # the output to a file, enable branching.
        # https://gstreamer.freedesktop.org/documentation/tutorials/basic/gstreamer-tools.html?gi-language=c#named-elements
        self.add_command('tee name=t')
        self.add_command('queue')

    def have_type(self, typefind, probability, caps):
        pass

    def query_position(self):
        """Ask for the stream position of the current pipeline."""
        try:
            if self.pipeline:
                self.position = max(0, self.pipeline.query_position(
                    Gst.Format.TIME)[1] / Gst.SECOND)
        except Gst.QueryError:
            self.position = 0

    def found_tag(self, decoder, something, taglist):
        """Called when the decoder reads a tag."""
        logger.debug('found_tag: {}'.format(self.sound_file.filename_for_display))
        taglist.foreach(self.append_tag, None)

    def append_tag(self, taglist, tag, unused_udata):
        tag_whitelist = (
            'album-artist',
            'artist',
            'album',
            'title',
            'track-number',
            'track-count',
            'genre',
            'datetime',
            'year',
            'timestamp',
            'album-disc-number',
            'album-disc-count',
        )
        if tag not in tag_whitelist:
            return

        tag_type = Gst.tag_get_type(tag)
        type_getters = {
            GObject.TYPE_STRING: 'get_string',
            GObject.TYPE_DOUBLE: 'get_double',
            GObject.TYPE_FLOAT: 'get_float',
            GObject.TYPE_INT: 'get_int',
            GObject.TYPE_UINT: 'get_uint',
        }

        tags = {}
        if tag_type in type_getters:
            value = str(getattr(taglist, type_getters[tag_type])(tag)[1])
            tags[tag] = value

        if 'datetime' in tag:
            dt = taglist.get_date_time(tag)[1]
            tags['year'] = dt.get_year()
            tags['date'] = dt.to_iso8601_string()[:10]

        logger.debug('    {}'.format(tags))
        self.sound_file.tags.update(tags)

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

    def get_duration(self):
        """Return the total duration of the sound file."""
        return self.sound_file.duration

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


class Converter(Decoder):
    """A background task for converting files to another format."""

    def __init__(self, sound_file, output_filename, output_type,
                 delete_original=False, output_resample=False,
                 resample_rate=48000, force_mono=False, ignore_errors=False):
        Decoder.__init__(self, sound_file)

        self.output_filename = output_filename
        self.output_type = output_type
        self.vorbis_quality = 0.6
        self.aac_quality = 192
        self.mp3_bitrate = 192
        self.mp3_mode = 'vbr'
        self.mp3_quality = 3
        self.flac_compression = 8
        self.wav_sample_width = 16

        self.output_resample = output_resample
        self.resample_rate = resample_rate
        self.force_mono = force_mono

        self.overwrite = False
        self.delete_original = delete_original

        self.ignore_errors = ignore_errors

        self.got_duration = False

    def init(self):
        self.encoders = {
            'audio/x-vorbis': self.add_oggvorbis_encoder,
            'audio/x-flac': self.add_flac_encoder,
            'audio/x-wav': self.add_wav_encoder,
            'audio/mpeg': self.add_mp3_encoder,
            'audio/x-m4a': self.add_aac_encoder,
            'audio/ogg; codecs=opus': self.add_opus_encoder,
            'gst-profile': self.add_audio_profile,
        }
        self.add_command('audiorate')
        self.add_command('audioconvert')
        self.add_command('audioresample')

        # audio resampling support
        if self.output_resample:
            self.add_command('audio/x-raw,rate={}'.format(self.resample_rate))
            self.add_command('audioconvert')
            self.add_command('audioresample')

        if self.force_mono:
            self.add_command('audio/x-raw,channels=1')
            self.add_command('audioconvert')

        encoder = self.encoders[self.output_type]()
        self.add_command(encoder)

        gfile = Gio.file_parse_name(self.output_filename)
        dirname = gfile.get_parent()
        if dirname and not dirname.query_exists(None):
            logger.info('Creating folder: \'{}\''.format(beautify_uri(dirname.get_uri())))
            if not dirname.make_directory_with_parents():
                show_error('Error', _("Cannot create \'{}\' folder.").format(beautify_uri(dirname)))
                return

        self.add_command('{} location="{}"'.format(
            gstreamer_sink, encode_filename(self.output_filename)
        ))
        if self.overwrite and vfs_exists(self.output_filename):
            logger.info('overwriting \'{}\''.format(beautify_uri(self.output_filename)))
            vfs_unlink(self.output_filename)
        
        # mp4mux drops tag events/messages
        # https://gitlab.freedesktop.org/gstreamer/gst-plugins-good/-/issues/759
        # Here is another branch of the pipeline without muxer, so that tags arrive
        # soundconverter no matter what the conversion pipeline does.
        self.add_command('t.', sep='')
        self.add_command('queue')
        self.add_command('fakesink')

    def aborted(self):
        # remove partial file
        try:
            vfs_unlink(self.output_filename)
        except Exception:
            logger.info('cannot delete: \'{}\''.format(beautify_uri(self.output_filename)))
        return

    def finished(self):
        Pipeline.finished(self)

        # Copy file permissions
        if not Gio.file_parse_name(self.sound_file.uri).copy_attributes(
                Gio.file_parse_name(self.output_filename), Gio.FileCopyFlags.NONE, None):
            logger.info('Cannot set permission on \'{}\''.format(beautify_uri(self.output_filename)))

        if self.delete_original and self.processing and not self.error:
            logger.info('deleting: \'{}\''.format(self.sound_file.uri))
            if not vfs_unlink(self.sound_file.uri):
                logger.info('Cannot remove \'{}\''.format(beautify_uri(self.output_filename)))

    def on_error(self, error):
        if self.ignore_errors:
            self.error = error
            logger.info('ignored-error: {} ({})'.format(error, self.command))
        else:
            Pipeline.on_error(self, error)
            show_error(
                '{}'.format(_('GStreamer Error:')),
                '{}\n({})'.format(error, self.sound_file.filename_for_display)
            )

    def set_vorbis_quality(self, quality):
        self.vorbis_quality = quality

    def set_aac_quality(self, quality):
        self.aac_quality = quality

    def set_opus_quality(self, quality):
        self.opus_quality = quality

    def set_mp3_mode(self, mode):
        self.mp3_mode = mode

    def set_mp3_quality(self, quality):
        self.mp3_quality = quality

    def set_flac_compression(self, compression):
        self.flac_compression = compression

    def set_wav_sample_width(self, sample_width):
        self.wav_sample_width = sample_width

    def set_audio_profile(self, audio_profile):
        self.audio_profile = audio_profile

    def add_flac_encoder(self):
        s = 'flacenc mid-side-stereo=true quality={}'.format(self.flac_compression)
        return s

    def add_wav_encoder(self):
        formats = {8: 'U8', 16: 'S16LE', 24: 'S24LE', 32: 'S32LE'}
        return 'audioconvert ! audio/x-raw,format={} ! wavenc'.format(formats[self.wav_sample_width])

    def add_oggvorbis_encoder(self):
        cmd = 'vorbisenc'
        if self.vorbis_quality is not None:
            cmd += ' quality={}'.format(self.vorbis_quality)
        cmd += ' ! oggmux '
        return cmd

    def add_mp3_encoder(self):
        cmd = 'lamemp3enc encoding-engine-quality=2 '

        if self.mp3_mode is not None:
            properties = {
                'cbr': 'target=bitrate cbr=true bitrate=%s ',
                'abr': 'target=bitrate cbr=false bitrate=%s ',
                'vbr': 'target=quality cbr=false quality=%s ',
            }

            cmd += properties[self.mp3_mode] % self.mp3_quality

            if 'xingmux' in available_elements and self.mp3_mode != 'cbr':
                # add xing header when creating VBR/ABR mp3
                cmd += '! xingmux '

        if 'id3mux' in available_elements:
            # add tags
            cmd += '! id3mux '
        elif 'id3v2mux' in available_elements:
            # add tags
            cmd += '! id3v2mux '

        return cmd

    def add_aac_encoder(self):
        encoder = 'faac' if 'faac' in available_elements else 'avenc_aac'
        return '{} bitrate={} ! mp4mux'.format(encoder, self.aac_quality * 1000)

    def add_opus_encoder(self):
        return 'opusenc bitrate={} bitrate-type=vbr bandwidth=auto ! oggmux'.format(self.opus_quality * 1000)

    def add_audio_profile(self):
        pipeline = audio_profiles_dict[self.audio_profile][2]
        return pipeline


class ConverterQueue(TaskQueue):
    """Background task for converting many files."""

    def __init__(self, window):
        TaskQueue.__init__(self)
        self.window = window
        self.overwrite_action = None
        self.reset_counters()

    def reset_counters(self):
        self.duration_processed = 0
        self.overwrite_action = None
        self.errors = []
        self.error_count = 0
        self.all_tasks = None
        global user_canceled_codec_installation
        user_canceled_codec_installation = True

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
        c.set_vorbis_quality(gio_settings.get_double('vorbis-quality'))
        c.set_aac_quality(gio_settings.get_int('aac-quality'))
        c.set_opus_quality(gio_settings.get_int('opus-bitrate'))
        c.set_flac_compression(gio_settings.get_int('flac-compression'))
        c.set_wav_sample_width(gio_settings.get_int('wav-sample-width'))
        c.set_audio_profile(gio_settings.get_string('audio-profile'))

        quality = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }
        mode = gio_settings.get_string('mp3-mode')
        c.set_mp3_mode(mode)
        c.set_mp3_quality(gio_settings.get_int(quality[mode]))
        c.init()
        c.add_listener('finished', self.on_task_finished)
        self.add_task(c)

    def get_progress(self, per_file_progress):
        tasks = self.running_tasks

        # try to get all tasks durations
        if not self.all_tasks:
            self.all_tasks = []
            self.all_tasks.extend(self.waiting_tasks)
            self.all_tasks.extend(self.running_tasks)

        for task in self.all_tasks:
            if task.sound_file.duration is None:
                duration = task.get_duration()

        position = 0.0
        prolist = [1] * self.finished_tasks
        for task in tasks:
            if task.running:
                task_position = task.get_position()
                position += task_position
                per_file_progress[task.sound_file] = None
                if task.sound_file.duration is None:
                    continue
                taskprogress = task_position / task.sound_file.duration
                taskprogress = min(max(taskprogress, 0.0), 1.0)
                prolist.append(taskprogress)
                per_file_progress[task.sound_file] = taskprogress
        for task in self.waiting_tasks:
            prolist.append(0.0)

        progress = sum(prolist) / len(prolist) if prolist else 0
        progress = min(max(progress, 0.0), 1.0)
        return self.running or len(self.all_tasks), progress

    def on_task_finished(self, task):
        task.sound_file.progress = 1.0

        if task.error:
            logger.debug('error in task, skipping rename: {}'.format(task.output_filename))
            if vfs_exists(task.output_filename):
                vfs_unlink(task.output_filename)
            self.errors.append(task.error)
            logger.info('Could not convert {}: {}'.format(beautify_uri(task.get_input_uri()), task.error))
            self.error_count += 1
            return

        duration = task.get_duration()
        if duration:
            self.duration_processed += duration

        # rename temporary file
        newname = self.window.prefs.generate_filename(task.sound_file)
        logger.info('newname {}'.format(newname))
        logger.debug('{} -> {}'.format(beautify_uri(task.output_filename), beautify_uri(newname)))

        # safe mode. generate a filename until we find a free one
        p, e = os.path.splitext(newname)
        p = p.replace('%', '%%')

        space = ' '
        if (get_gio_settings().get_boolean('replace-messy-chars')):
            space = '_'

        p = p + space + '(%d)' + e

        i = 1
        while vfs_exists(newname):
            newname = p % i
            i += 1

        try:
            vfs_rename(task.output_filename, newname)
        except Exception:
            self.errors.append(task.error)
            logger.info('Could not rename {} to {}:'.format(beautify_uri(task.output_filename), beautify_uri(newname)))
            logger.info(traceback.print_exc())
            self.error_count += 1
            return

        logger.info('Converted {} to {}'.format(beautify_uri(task.get_input_uri()), beautify_uri(newname)))

    def finished(self):
        # This must be called with emit_async
        if self.running_tasks:
            raise RuntimeError
        TaskQueue.finished(self)
        self.window.set_sensitive()
        self.window.conversion_ended()
        total_time = self.run_finish_time - self.run_start_time
        msg = _('Conversion done in %s') % self.format_time(total_time)
        if self.error_count:
            msg += ', {} error(s)'.format(self.error_count)
        self.window.set_status(msg)
        if not self.window.is_active():
            notification(msg)  # this must move
        self.reset_counters()

    def format_time(self, seconds):
        units = [(86400, 'd'),
                 (3600, 'h'),
                 (60, 'm'),
                 (1, 's')]
        seconds = round(seconds)
        result = []
        for factor, unity in units:
            count = int(seconds / factor)
            seconds -= count * factor
            if count > 0 or (factor == 1 and not result):
                result.append('{} {}'.format(count, unity))
        assert seconds == 0
        return ' '.join(result)

    def abort(self):
        TaskQueue.abort(self)
        self.window.set_sensitive()
        self.reset_counters()

    def start(self):
        # self.waiting_tasks.sort(key=Converter.get_duration, reverse=True)
        TaskQueue.start(self)
