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


import os
import sys
import traceback
import time
from fnmatch import fnmatch
from urllib.parse import urlparse
from gettext import gettext as _

from gi.repository import Gst, Gtk, GLib, GObject, Gio

from soundconverter.util.fileoperations import vfs_encode_filename, unquote_filename, vfs_unlink, vfs_rename, \
    vfs_exists, beautify_uri
from soundconverter.util.task import BackgroundTask
from soundconverter.util.queue import TaskQueue
from soundconverter.util.logger import logger
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.formats import mime_whitelist, filename_blacklist
from soundconverter.util.error import show_error
from soundconverter.audio.task import Task
from soundconverter.interface.notify import notification


gstreamer_source = 'giosrc'
gstreamer_sink = 'giosink'

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


def create_flac_encoder():
    flac_compression = gio_settings.get_int('flac-compression')
    s = 'flacenc mid-side-stereo=true quality={}'.format(flac_compression)
    return s


def create_wav_encoder():
    wav_sample_width = gio_settings.get_int('wav-sample-width')
    formats = {8: 'u8', 16: 's16le', 24: 's24le', 32: 's32le'}
    return 'audioconvert ! audio/x-raw,format={} ! wavenc'.format(
        formats[wav_sample_width]
    )


def create_oggvorbis_encoder():
    cmd = 'vorbisenc'
    vorbis_quality = gio_settings.get_double('vorbis-quality')
    if vorbis_quality is not None:
        cmd += ' quality={}'.format(vorbis_quality)
    cmd += ' ! oggmux '
    return cmd


def create_mp3_encoder():
    quality = {
        'cbr': 'mp3-cbr-quality',
        'abr': 'mp3-abr-quality',
        'vbr': 'mp3-vbr-quality'
    }
    mode = gio_settings.get_string('mp3-mode')

    mp3_mode = mode
    mp3_quality = gio_settings.get_int(quality[mode])

    cmd = 'lamemp3enc encoding-engine-quality=2 '

    if mp3_mode is not None:
        properties = {
            'cbr': 'target=bitrate cbr=true bitrate=%s ',
            'abr': 'target=bitrate cbr=false bitrate=%s ',
            'vbr': 'target=quality cbr=false quality=%s ',
        }

        cmd += properties[mp3_mode] % mp3_quality

        if 'xingmux' in available_elements and mp3_mode != 'cbr':
            # add xing header when creating vbr/abr mp3
            cmd += '! xingmux '

    if 'id3mux' in available_elements:
        # add tags
        cmd += '! id3mux '
    elif 'id3v2mux' in available_elements:
        # add tags
        cmd += '! id3v2mux '

    return cmd


def create_aac_encoder():
    aac_quality = gio_settings.get_int('aac-quality')
    encoder = 'faac' if 'faac' in available_elements else 'avenc_aac'
    return '{} bitrate={} ! mp4mux'.format(encoder, aac_quality * 1000)


def create_opus_encoder():
    opus_quality = gio_settings.get_int('opus-bitrate')
    return (
        'opusenc bitrate={} bitrate-type=vbr '
        'bandwidth=auto ! oggmux'
    ).format(opus_quality * 1000)


def create_audio_profile():
    audio_profile = gio_settings.get_string('audio-profile')
    pipeline = audio_profiles_dict[audio_profile][2]
    return pipeline


class Converter(Task):
    def __init__(self, sound_file, output_filename, output_type,
                 delete_original=False, output_resample=False,
                 resample_rate=48000, force_mono=False, ignore_errors=False):
        """create a converter that converts a single file."""
        self.output_filename = output_filename
        self.output_type = output_type

        self.output_resample = output_resample
        self.resample_rate = resample_rate
        self.force_mono = force_mono

        self.overwrite = False
        self.delete_original = delete_original

        self.ignore_errors = ignore_errors

        self.got_duration = False

        self.command = []

        self.sound_file = sound_file
        self.time = 0
        self.position = 0

        self.pipeline = None
        self.done = False

    def get_progress(self):
        """Fraction of how much of the task is completed."""
        if self.sound_file.duration is None:
            duration = self.get_duration()

        position = 0.0
        prolist = [1] * self.finished_tasks
        if not self.done:
            task_position = self.get_position()
            position += task_position
            per_file_progress[self.sound_file] = None
            if self.sound_file.duration is None:
                continue
            taskprogress = task_position / self.sound_file.duration
            taskprogress = min(max(taskprogress, 0.0), 1.0)
            prolist.append(taskprogress)
            per_file_progress[self.sound_file] = taskprogress
        for self in self.waiting_tasks:
            prolist.append(0.0)

        progress = sum(prolist) / len(prolist) if prolist else 0
        progress = min(max(progress, 0.0), 1.0)
        return self.running or len(self.all_tasks), progress

    def cancel(self):
        """Cancel execution of the task."""
        raise NotImplementedError()

    def pause(self):
        """Pause execution of the task."""
        if not self.pipeline:
            logger.debug('pause(): pipeline is None!')
            return
        self.pipeline.set_state(Gst.State.PAUSED)

    def resume(self):
        """Resume execution of the task."""
        if not self.pipeline:
            logger.debug('resume(): pipeline is None!')
            return
        self.pipeline.set_state(Gst.State.PLAYING)

    def _convert(self, command):
        """Run the gst pipeline that converts files.
        
        Parameters
        ----------
            command : string
                gstreamer command
        """
        if self.pipeline is None:
            logger.debug('launching: \'{}\''.format(command))
            try:
                # see https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html
                self.pipeline = Gst.parse_launch(command)
                bus = self.pipeline.get_bus()
                # TODO connect is not documented. And what is get_by_name
                bus.connect('finished', self._conversion_done)

                # TODO connected_signals needed?
                assert not self.connected_signals
                self.connected_signals = []
                # TODO needed for-loop?
                # Or does calling bus.connect manually suffice?
                for name, signal, callback in self.signals:
                    if name:
                        element = self.pipeline.get_by_name(name)
                    else:
                        element = bus
                    sid = element.connect(signal, callback)
                    self.connected_signals.append((element, sid,))

            except GLib.gerror as e:
                show_error('gstreamer error when creating pipeline', str(e))
                self.error = str(e)
                self.eos = True
                self.done()
                return

            bus.add_signal_watch()
            self.watch_id = bus.connect('message', self.on_message)

        self.pipeline.set_state(Gst.state.playing)

    def _conversion_done(self):
        """Called by gstreamer when the conversion is done.
        
        Renames the temporary file to the final file.
        """
        task.sound_file.progress = 1.0

        if self.error:
            logger.debug('error in task, skipping rename: {}'.format(self.output_filename))
            if vfs_exists(self.output_filename):
                vfs_unlink(self.output_filename)
            self.errors.append(self.error)
            logger.info('Could not convert {}: {}'.format(beautify_uri(self.get_input_uri()), self.error))
            self.error_count += 1
            return

        duration = self.get_duration()
        if duration:
            self.duration_processed += duration

        # rename temporary file
        newname = self.window.prefs.generate_filename(self.sound_file)
        logger.info('newname {}'.format(newname))
        logger.debug('{} -> {}'.format(beautify_uri(self.output_filename), beautify_uri(newname)))

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
            vfs_rename(self.output_filename, newname)
        except Exception:
            self.errors.append(self.error)
            logger.info('Could not rename {} to {}:'.format(
                beautify_uri(self.output_filename), beautify_uri(newname)
            ))
            logger.info(traceback.print_exc())
            self.error_count += 1
            return

        logger.info('Converted {} to {}'.format(
            beautify_uri(self.get_input_uri()), beautify_uri(newname)
        ))
        
        # Copy file permissions
        if not Gio.file_parse_name(self.sound_file.uri).copy_attributes(
                Gio.file_parse_name(self.output_filename), Gio.FileCopyFlags.NONE, None):
            logger.info('Cannot set permission on \'{}\''.format(beautify_uri(self.output_filename)))

        if self.delete_original and self.processing and not self.error:
            logger.info('deleting: \'{}\''.format(self.sound_file.uri))
            if not vfs_unlink(self.sound_file.uri):
                logger.info('Cannot remove \'{}\''.format(beautify_uri(self.output_filename)))

        self.done = True

    def run(self, callback):
        """Call this in order to run the whole Converter task.

        parameters
        ----------
            callback : function
                call this when done
        """
        # construct a pipeline for conversion
        command = []

        # Add default decoding step that remains the same for all formats.
        command.push(
            '{} location="{}" name=src ! decodebin name=decoder'.format(
                gstreamer_source, vfs_encode_filename(self.sound_file.uri)
            )
        )

        command.push('audiorate ! audioconvert ! audioresample')

        # audio resampling support
        if self.output_resample:
            command.push('audio/x-raw,rate={}'.format(self.resample_rate))
            command.push('audioconvert ! audioresample')

        if self.force_mono:
            command.push('audio/x-raw,channels=1 | audioconvert')

        # figure out the rest of the gst pipeline string
        encoder = {
            'audio/x-vorbis': create_oggvorbis_encoder,
            'audio/x-flac': create_flac_encoder,
            'audio/x-wav': create_wav_encoder,
            'audio/mpeg': create_mp3_encoder,
            'audio/x-m4a': create_aac_encoder,
            'audio/ogg; codecs=opus': create_opus_encoder,
            'gst-profile': create_audio_profile,
        }[self.output_type]()
        command.push(encoder)

        # output file
        gfile = Gio.file_parse_name(self.output_filename)
        dirname = gfile.get_parent()
        if dirname and not dirname.query_exists(None):
            logger.info('creating folder: \'{}\''.format(beautify_uri(dirname.get_uri())))
            if not dirname.make_directory_with_parents():
                show_error('error', _("cannot create \'{}\' folder.").format(beautify_uri(dirname)))
                return

        command.push('{} location="{}"'.format(
            gstreamer_sink, vfs_encode_filename(self.output_filename))
        )

        if self.overwrite and vfs_exists(self.output_filename):
            logger.info('overwriting \'{}\''.format(beautify_uri(self.output_filename)))
            vfs_unlink(self.output_filename)

        # preparation done, now convert
        self._convert(command.join(' ! '))
