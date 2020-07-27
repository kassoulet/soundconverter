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
import traceback
from gettext import gettext as _

from gi.repository import Gst, GLib, Gio

from soundconverter.util.fileoperations import vfs_encode_filename, \
    vfs_unlink, vfs_rename, vfs_exists, beautify_uri
from soundconverter.util.logger import logger
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.error import show_error
from soundconverter.util.names import generate_filename
from soundconverter.audio.task import Task
from soundconverter.audio.profiles import audio_profiles_dict


GSTREAMER_SOURCE = 'giosrc'
GSTREAMER_SINK = 'giosink'


def find_available_elements():
    """Figure out which gstreamer pipeline plugins are available."""
    # gst-plugins-good, gst-plugins-bad, etc. packages provide them
    available_elements = set()
    functions = dict()

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

    return available_elements, functions


available_elements, functions = find_available_elements()


def create_flac_encoder():
    """Return an flac encoder for the gst pipeline string."""
    flac_compression = get_gio_settings().get_int('flac-compression')
    return 'flacenc mid-side-stereo=true quality={}'.format(flac_compression)


def create_wav_encoder():
    """Return a wav encoder for the gst pipeline string."""
    wav_sample_width = get_gio_settings().get_int('wav-sample-width')
    formats = {8: 'u8', 16: 's16le', 24: 's24le', 32: 's32le'}
    return 'audioconvert ! audio/x-raw,format={} ! wavenc'.format(
        formats[wav_sample_width]
    )


def create_oggvorbis_encoder():
    """Return an ogg encoder for the gst pipeline string."""
    cmd = 'vorbisenc'
    vorbis_quality = get_gio_settings().get_double('vorbis-quality')
    if vorbis_quality is not None:
        cmd += ' quality={}'.format(vorbis_quality)
    cmd += ' ! oggmux '
    return cmd


def create_mp3_encoder():
    """Return an mp3 encoder for the gst pipeline string."""
    quality = {
        'cbr': 'mp3-cbr-quality',
        'abr': 'mp3-abr-quality',
        'vbr': 'mp3-vbr-quality'
    }
    mode = get_gio_settings().get_string('mp3-mode')

    mp3_mode = mode
    mp3_quality = get_gio_settings().get_int(quality[mode])

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
    """Return an aac encoder for the gst pipeline string."""
    aac_quality = get_gio_settings().get_int('aac-quality')
    encoder = 'faac' if 'faac' in available_elements else 'avenc_aac'
    return '{} bitrate={} ! mp4mux'.format(encoder, aac_quality * 1000)


def create_opus_encoder():
    """Return an opus encoder for the gst pipeline string."""
    opus_quality = get_gio_settings().get_int('opus-bitrate')
    return (
        'opusenc bitrate={} bitrate-type=vbr '
        'bandwidth=auto ! oggmux'
    ).format(opus_quality * 1000)


def create_audio_profile():
    """TODO."""
    audio_profile = get_gio_settings().get_string('audio-profile')
    pipeline = audio_profiles_dict[audio_profile][2]
    return pipeline


class Converter(Task):
    """Completely handle the conversion of a single file."""

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

        self.command = None

        self.sound_file = sound_file
        self.time = 0
        self.position = 0

        self.pipeline = None
        self.done = False

    def _query_position(self):
        """Ask for the stream position of the current pipeline."""
        try:
            if self.pipeline:
                return max(
                    0, self.pipeline.query_position(
                        Gst.Format.TIME
                    )[1] / Gst.SECOND
                )
        except Gst.QueryError:
            return 0

    def get_progress(self):
        """Fraction of how much of the task is completed."""
        if not self.done:
            position = self._query_position()
            if self.sound_file.duration is None:
                return 0
            progress = position / self.sound_file.duration
            progress = min(max(progress, 0.0), 1.0)
            return progress
        else:
            return 1

    def cancel(self):
        """Cancel execution of the task."""
        # remove partial file
        try:
            vfs_unlink(self.output_filename)
        except Exception:
            logger.info('cannot delete: \'{}\''.format(beautify_uri(self.output_filename)))
        return

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

    def _convert(self):
        """Run the gst pipeline that converts files.

        Handlers for messages sent from gst are added, which also triggers
        renaming the file to it's final path.
        """
        command = self.command
        if self.pipeline is None:
            logger.debug('launching: \'{}\''.format(command))
            try:
                # see https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html
                self.pipeline = Gst.parse_launch(command)
                bus = self.pipeline.get_bus()

                # TODO there once was connected_signals stuff
                # TODO there once was
                # `for name, signal, callback in self.signals:`

            except GLib.gerror as e:
                show_error('gstreamer error when creating pipeline', str(e))
                self.error = str(e)
                self.eos = True
                self.done()
                return

            bus.add_signal_watch()
            self.watch_id = bus.connect('message', self._on_message)

        self.pipeline.set_state(Gst.state.playing)

    def _conversion_done(self):
        """Rename the temporary file to the final file.
        
        Should be called when the EOS message arrived.
        """
        task.sound_file.progress = 1.0

        input_uri = self.sound_file.uri

        if self.error:
            logger.debug('error in task, skipping rename: {}'.format(
                self.output_filename
            ))

            if vfs_exists(self.output_filename):
                vfs_unlink(self.output_filename)

            logger.info('Could not convert {}: {}'.format(
                beautify_uri(input_uri), self.error
            ))

            return

        duration = self.sound_file.duration
        if duration:
            self.duration_processed += duration

        # rename temporary file
        newname = generate_filename(self.sound_file)
        logger.info('newname {}'.format(newname))
        logger.debug('{} -> {}'.format(beautify_uri(self.output_filename), beautify_uri(newname)))

        # safe mode. generate a filename until we find a free one
        path, path = os.path.splitext(newname)
        path = path.replace('%', '%%')

        space = ' '
        if get_gio_settings().get_boolean('replace-messy-chars'):
            space = '_'

        path = path + space + '(%d)' + path

        i = 1
        while vfs_exists(newname):
            newname = path % i
            i += 1

        try:
            vfs_rename(self.output_filename, newname)
        except Exception as e:
            self.error = str(e)
            logger.info('Could not rename {} to {}:'.format(
                beautify_uri(self.output_filename), beautify_uri(newname)
            ))
            logger.info(traceback.print_exc())
            return

        logger.info('Converted {} to {}'.format(
            beautify_uri(input_uri), beautify_uri(newname)
        ))
        
        # Copy file permissions
        if not Gio.file_parse_name(self.sound_file.uri).copy_attributes(
                Gio.file_parse_name(self.output_filename), Gio.FileCopyFlags.NONE, None):
            logger.info('Cannot set permission on \'{}\''.format(beautify_uri(self.output_filename)))

        # TODO had `and self.processing and`
        if self.delete_original and not self.error:
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
        command.append(
            '{} location="{}" name=src ! decodebin name=decoder'.format(
                GSTREAMER_SOURCE, vfs_encode_filename(self.sound_file.uri)
            )
        )

        command.append('audiorate ! audioconvert ! audioresample')

        # audio resampling support
        if self.output_resample:
            command.append('audio/x-raw,rate={}'.format(self.resample_rate))
            command.append('audioconvert ! audioresample')

        if self.force_mono:
            command.append('audio/x-raw,channels=1 ! audioconvert')

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
        command.append(encoder)

        # temporary output file. Until the file is handled by gstreamer,
        # its tags are unknown, so the correct output path cannot be
        # constructed yet.
        gfile = Gio.file_parse_name(self.output_filename)
        dirname = gfile.get_parent()
        if dirname and not dirname.query_exists(None):
            logger.info('creating folder: \'{}\''.format(
                beautify_uri(dirname.get_uri())
            ))
            if not dirname.make_directory_with_parents():
                show_error(
                    'error',
                    _('cannot create \'{}\' folder.').format(
                        beautify_uri(dirname)
                    )
                )
                return

        command.append('{} location="{}"'.format(
            GSTREAMER_SINK, vfs_encode_filename(self.output_filename))
        )

        if self.overwrite and vfs_exists(self.output_filename):
            logger.info('overwriting \'{}\''.format(beautify_uri(self.output_filename)))
            vfs_unlink(self.output_filename)

        # preparation done, now convert
        self.command = ' ! '.join(command)
        self._convert()

    def _on_error(self, error):
        """Log errors and write down that this Task failed.

        The TaskQueue is interested in reading the error.
        """
        self.error = error
        # TODO both logger.error and stderr in show_error?
        logger.error('{} '.format(error, ' ! '.join(self.command)))
        show_error(
            '{}'.format(_('GStreamer Error:')),
            '{}\n({})'.format(error, self.sound_file.filename_for_display)
        )

    def _on_message(self, bus, message):
        """Handle message events sent by gstreamer."""
        t = message.type
        if t == Gst.MessageType.ERROR:
            error, __ = message.parse_error()
            self._on_error(error)
        elif t == Gst.MessageType.EOS:
            # Conversion done
            self._conversion_done()
        elif t == Gst.MessageType.TAG:
            self.found_tag(self, '', message.parse_tag())

    def _found_tag(self, decoder, something, taglist):
        """Called when the decoder reads a tag.
        
        TODO params
        """
        logger.debug(
            'found_tag: {}'.format(self.sound_file.filename_for_display)
        )

        # TODO normal for loop possible?
        # pasting _append_tag into it's inner scope?
        print('taglist', type(taglist))
        taglist.foreach(self._append_tag, None)

    def _append_tag(self, taglist, tag, unused_udata):
        """TODO docstring
        
        TODO params
        """
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
        # TODO tag whitelist needed? It's only for constructing the path
        # anyway. Does the ui has some sort of list itself of which
        # tags are legal? (redundant? or does it depend on the tag_whitelist
        # around some corners?)
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
