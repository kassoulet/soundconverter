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
from gettext import gettext as _

from gi.repository import Gst, GLib, Gio

from soundconverter.util.fileoperations import vfs_encode_filename, \
    vfs_unlink, vfs_rename, vfs_exists, beautify_uri
from soundconverter.util.logger import logger
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.error import show_error
from soundconverter.util.task import Task


GSTREAMER_SOURCE = 'giosrc'
GSTREAMER_SINK = 'giosink'

available_elements = set()


def find_available_elements():
    """Figure out which gstreamer pipeline plugins are available."""
    # gst-plugins-good, gst-plugins-bad, etc. packages provide them
    global available_elements

    GOOD = 'gst-plugins-good'
    BAD = 'gst-plugins-bad'
    BASE = 'gst-plugins-base'
    UGLY = 'gst-plugins-ugly'
    LIBAV = 'gst-libav'

    # some functions can be provided by various packages.
    # move preferred packages towards the bottom.
    encoders = [
        ('asfmux', 'WMA', 'wma-enc', BAD),
        ('avenc_wmav2', 'WMA', 'wma-enc', LIBAV),
        ('flacenc', 'FLAC', 'flac-enc', GOOD),
        ('wavenc', 'WAV', 'wav-enc', GOOD),
        ('vorbisenc', 'Ogg Vorbis', 'vorbis-enc', BASE),
        ('oggmux', 'Ogg Vorbis', 'vorbis-mux', BASE),
        ('id3mux', 'MP3 tags', 'mp3-id-tags', BAD),
        ('id3v2mux', 'MP3 tags', 'mp3-id-tags', GOOD),
        ('xingmux', 'VBR tags', 'mp3-vbr-tags', UGLY),
        ('lamemp3enc', 'MP3', 'mp3-enc', GOOD),
        ('mp4mux', 'AAC', 'aac-mux', GOOD),
        ('opusenc', 'Opus', 'opus-enc', BASE),
        ('faac', 'AAC', 'aac-enc', BAD),
        ('avenc_aac', 'AAC', 'aac-enc', LIBAV),
        ('fdkaacenc', 'AAC', 'aac-enc', BAD),
    ]

    result = dict()
    for encoder, name, function, package in encoders:
        have_it = bool(Gst.ElementFactory.find(encoder))
        if have_it:
            available_elements.add(encoder)
        else:
            logger.debug(
                '{} gstreamer element from "{}" not found\n'.format(
                    encoder,
                    package
                )
            )
        result[function] = (have_it, package)

    for function in result:
        have_it, package = result[function]
        if not have_it:
            logger.error(
                'Disabling {} output. Do you have "{}" installed?'.format(
                    function,
                    package
                )
            )

    if 'oggmux' not in available_elements:
        available_elements.discard('vorbisenc')
    if 'mp4mux' not in available_elements:
        available_elements.discard('faac')
        available_elements.discard('avenc_aac')
    if 'asfmux' not in available_elements:
        available_elements.discard('avenc_wmav2')


find_available_elements()


def create_flac_encoder():
    """Return an flac encoder for the gst pipeline string."""
    flac_compression = get_gio_settings().get_int('flac-compression')
    return 'flacenc mid-side-stereo=true quality={}'.format(flac_compression)


def create_wav_encoder():
    """Return a wav encoder for the gst pipeline string."""
    wav_sample_width = get_gio_settings().get_int('wav-sample-width')
    formats = {8: 'U8', 16: 'S16LE', 24: 'S24LE', 32: 'S32LE'}
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

    # it seemed like I couldn't get vbr to work with any of these, not even
    # with rate-control and quality of faac or with maxrate of avenc_aac.
    # Or it was audacious not displaying the current vbr rate correctly.
    bitrate = aac_quality * 1000

    # list of recommended aac encoders:
    # https://wiki.hydrogenaud.io/index.php?title=AAC_encoders
    if 'fdkaacenc' in available_elements:
        return 'fdkaacenc bitrate={} ! mp4mux'.format(bitrate)

    encoder = 'faac' if 'faac' in available_elements else 'avenc_aac'
    logger.warning(
        'fdkaacenc is recommended for aac conversion but it is not '
        'available. It can be installed with gst-plugins-bad. '
        'Using {} instead.'.format(encoder)
    )

    if 'faac' in available_elements:
        return 'faac bitrate={} rate-control=2 ! mp4mux'.format(bitrate)

    return 'avenc_aac bitrate={} ! mp4mux'.format(bitrate)


def create_opus_encoder():
    """Return an opus encoder for the gst pipeline string."""
    opus_quality = get_gio_settings().get_int('opus-bitrate')
    return (
        'opusenc bitrate={} bitrate-type=vbr '
        'bandwidth=auto ! oggmux'
    ).format(opus_quality * 1000)

def create_wma_encoder():
    """Return an wma encoder for the gst pipeline string."""
    wma_quality = get_gio_settings().get_int('wma-bitrate')
    return (
        'avenc_wmav2 bitrate={} ! asfmux'
    ).format(wma_quality * 1000)

class Converter(Task):
    """Completely handle the conversion of a single file."""
    INCREMENT = 'increment'
    OVERWRITE = 'overwrite'
    SKIP = 'skip'

    def __init__(self, sound_file, name_generator):
        """create a converter that converts a single file.

        Parameters
        ----------
        name_generator : TargetNameGenerator
            TargetNameGenerator that creates filenames for all converters
            of the current TaskQueue
        """
        # Configuration
        self.sound_file = sound_file
        self.temporary_filename = None
        self.newname = None
        self.existing_behaviour = Converter.INCREMENT
        self.name_generator = name_generator

        # All relevant gio settings have to be copied and remembered, so that
        # they don't suddenly change during the conversion
        settings = get_gio_settings()
        self.output_mime_type = settings.get_string('output-mime-type')
        self.output_resample = settings.get_boolean('output-resample')
        self.resample_rate = settings.get_int('resample-rate')
        self.force_mono = settings.get_boolean('force-mono')
        self.replace_messy_chars = settings.get_boolean('replace-messy-chars')
        self.delete_original = settings.get_boolean('delete-original')

        # State
        self.command = None
        self.pipeline = None
        self._done = False
        self.error = None
        self.output_uri = None

        super().__init__()

    def _query_position(self):
        """Ask for the stream position of the current pipeline."""
        if self.pipeline:
            # during Gst.State.PAUSED it returns super small numbers,
            # so take care
            position = self.pipeline.query_position(Gst.Format.TIME)[1]
            return max(0, position / Gst.SECOND)
        return 0

    def get_progress(self):
        """Fraction of how much of the task is completed."""
        duration = self.sound_file.duration

        if self._done:
            return 1, duration

        if self.pipeline is None or duration is None:
            return 0, duration

        position = self._query_position()
        progress = position / duration if duration else 0
        progress = min(max(progress, 0.0), 1.0)
        return progress, duration

    def cancel(self):
        """Cancel execution of the task."""
        self._stop_pipeline()
        self.done()

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

    def _cleanup(self):
        """Delete the pipeline."""
        if self.pipeline is not None:
            bus = self.pipeline.get_bus()
            if hasattr(self, 'watch_id'):
                bus.disconnect(self.watch_id)
                bus.remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

    def _stop_pipeline(self):
        # remove partial file
        if self.temporary_filename is not None:
            if vfs_exists(self.temporary_filename):
                try:
                    vfs_unlink(self.temporary_filename)
                except Exception as error:
                    logger.error('cannot delete: \'{}\': {}'.format(
                        beautify_uri(self.temporary_filename),
                        str(error)
                    ))
        if not self.pipeline:
            logger.debug('pipeline already stopped!')
            return
        self._cleanup()

    def _convert(self):
        """Run the gst pipeline that converts files.

        Handlers for messages sent from gst are added, which also triggers
        renaming the file to it's final path.
        """
        command = self.command
        if self.pipeline is None:
            logger.debug('launching: \'{}\''.format(command))
            try:
                self.pipeline = Gst.parse_launch(command)
                bus = self.pipeline.get_bus()
            except GLib.Error as error:
                self.error = 'gstreamer error when creating pipeline: {}'.format(str(error))
                self._on_error(self.error)
                return

            bus.add_signal_watch()
            self.watch_id = bus.connect('message', self._on_message)

        self.pipeline.set_state(Gst.State.PLAYING)

    def _conversion_done(self):
        """Should be called when the EOS message arrived or on error.

        Will clear the temporary data on error or move the temporary file
        to the final path on success.
        """
        input_uri = self.sound_file.uri
        newname = self.newname

        if newname is None:
            raise AssertionError('the conversion was not started')

        if self.error:
            logger.debug('error in task, skipping rename: {}'.format(
                self.temporary_filename
            ))
            vfs_unlink(self.temporary_filename)
            logger.error('could not convert {}: {}'.format(
                beautify_uri(input_uri),
                self.error
            ))
            self.done()
            return

        if not vfs_exists(self.temporary_filename):
            self.error = 'Expected {} to exist after conversion.'.format(
                self.temporary_filename
            )
            self.done()
            return

        # rename temporary file
        logger.debug('{} -> {}'.format(
            beautify_uri(self.temporary_filename), beautify_uri(newname)
        ))

        path, extension = os.path.splitext(newname)
        path = path.replace('%', '%%')

        space = ' '
        if self.replace_messy_chars:
            space = '_'

        exists = vfs_exists(newname)
        if self.existing_behaviour == Converter.INCREMENT and exists:
            # If the file already exists, increment the filename so that
            # nothing gets overwritten.
            path = path + space + '(%d)' + extension
            i = 1
            while vfs_exists(newname):
                newname = path % i
                i += 1

        try:
            if self.existing_behaviour == Converter.OVERWRITE and exists:
                logger.info('overwriting \'{}\''.format(
                    beautify_uri(newname)
                ))
                vfs_unlink(newname)
            vfs_rename(self.temporary_filename, newname)
        except Exception as error:
            self.error = str(error)
            logger.error("could not rename '{}' to '{}': {}".format(
                beautify_uri(self.temporary_filename),
                beautify_uri(newname),
                str(error)
            ))
            self.done()
            return

        assert vfs_exists(newname)

        logger.info("converted '{}' to '{}'".format(
            beautify_uri(input_uri), beautify_uri(newname)
        ))

        # finish up the target file
        try:
            # Copy file permissions
            source = Gio.file_parse_name(self.sound_file.uri)
            destination = Gio.file_parse_name(newname)
            source.copy_attributes(destination, Gio.FileCopyFlags.ALL_METADATA)
        except Exception as error:
            logger.error(
                "Could not set some attributes of the target '{}': {}".format(
                    beautify_uri(newname),
                    str(error)
                )
            )
        try:
            # the modification date of the destination should be now
            info = Gio.FileInfo()
            now = GLib.DateTime.new_now(GLib.TimeZone())
            if callable(getattr(info, 'set_modification_date_time', None)):
                info.set_modification_date_time(now)
            else:
                # deprecated method
                timeval = GLib.TimeVal()
                now.to_timeval(timeval)
                info.set_modification_time(timeval)

            destination.set_attributes_from_info(
                info,
                Gio.FileQueryInfoFlags.NONE
            )
        except Exception as error:
            logger.error(
                "Could not set modification time of the target '{}': {}".format(
                    beautify_uri(newname),
                    str(error)
                )
            )

        if self.delete_original and not self.error:
            logger.info("deleting: '{}'".format(self.sound_file.uri))
            try:
                vfs_unlink(self.sound_file.uri)
            except Exception as error:
                logger.info("cannot remove '{}': {}".format(
                    beautify_uri(self.sound_file.uri),
                    str(error)
                ))

        self.output_uri = newname
        self.done()

    def done(self):
        self._done = True
        self._cleanup()
        super().done()

    def run(self):
        """Call this in order to run the whole Converter task."""
        self.newname = self.name_generator.generate_target_uri(
            self.sound_file
        )

        # temporary output file, in order to easily remove it without
        # any overwritten file and therefore caused damage in the target dir.
        self.temporary_filename = self.name_generator.generate_temp_path(
            self.sound_file
        )

        exists = vfs_exists(self.newname)
        if self.existing_behaviour == Converter.SKIP and exists:
            logger.info('output file already exists, skipping \'{}\''.format(
                beautify_uri(self.newname)
            ))
            self.done()
            return

        # construct a pipeline for conversion
        # Add default decoding step that remains the same for all formats.
        command = ['{} location="{}" name=src ! decodebin name=decoder'.format(
            GSTREAMER_SOURCE, vfs_encode_filename(self.sound_file.uri)
        ), 'audiorate ! audioconvert ! audioresample']

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
            'audio/x-ms-wma': create_wma_encoder
        }[self.output_mime_type]()
        command.append(encoder)

        gfile = Gio.file_parse_name(self.temporary_filename)
        dirname = gfile.get_parent()
        if dirname and not dirname.query_exists(None):
            logger.info('creating folder: \'{}\''.format(
                beautify_uri(dirname.get_uri())
            ))
            if not dirname.make_directory_with_parents():
                show_error(
                    _('cannot create \'{}\' folder.').format(
                        beautify_uri(dirname)
                    )
                )
                return

        command.append('{} location="{}"'.format(
            GSTREAMER_SINK, vfs_encode_filename(self.temporary_filename)
        ))

        # preparation done, now convert
        self.command = ' ! '.join(command)
        self._convert()

    def _on_error(self, error):
        """Log errors and write down that this Task failed.

        The TaskQueue is interested in reading the error.
        """
        self.error = error
        show_error(
            error,
            beautify_uri(self.sound_file.uri)
        )
        self._stop_pipeline()
        self.done()

    def _on_message(self, _, message):
        """Handle message events sent by gstreamer.

        Parameters
        ----------
        message : Gst.Message
        """
        if message.type == Gst.MessageType.ERROR:
            error, __ = message.parse_error()
            self._on_error(error)
        elif message.type == Gst.MessageType.EOS:
            # Conversion done
            self._conversion_done()
