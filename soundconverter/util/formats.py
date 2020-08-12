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


from soundconverter.util.settings import get_gio_settings
from soundconverter.util.logger import logger


filename_denylist = (
    '*.iso',
)


def get_mime_type_mapping():
    """Return a mapping of file extension to mime type."""
    mime_types = {
        'ogg': 'audio/x-vorbis', 'flac': 'audio/x-flac', 'wav': 'audio/x-wav',
        'mp3': 'audio/mpeg', 'aac': 'audio/x-m4a', 'm4a': 'audio/x-m4a',
        'opus': 'audio/ogg; codecs=opus'
    }
    return mime_types


def get_mime_type(audio_format):
    """Return the matching mime-type or None if it is not supported.

    Parameters
    ----------
    audio_format : string
        for example 'mp3' or 'audio/mpeg' for which the result would
        be 'audio/mpeg'
    """
    mime_types = get_mime_type_mapping()
    if audio_format not in mime_types.values():
        # possibly a file extension
        return mime_types.get(audio_format, None)
    else:
        # already a mime string
        return audio_format


def get_file_extension(mime):
    """Return the matching file extension or '?' if it is not supported.

    Examples: 'mp3', 'flac'.

    Parameters
    ----------
    mime : string
        mime string (like 'audio/x-m4a')
    """
    mime_types = get_mime_type_mapping()
    if mime in mime_types:
        # already an extension
        suffix = mime
        if suffix == 'ogg':
            if get_gio_settings().get_boolean('vorbis-oga-extension'):
                suffix = 'oga'
        return suffix
    else:
        mime2ext = {mime: ext for ext, mime in mime_types.items()}
        return mime2ext.get(mime, '?')


def get_quality_setting_name():
    """Get the settings name for quality for the set output-mime-type."""
    settings = get_gio_settings()
    mime_type = settings.get_string('output-mime-type')
    if mime_type == 'audio/mpeg':
        mode = settings.get_string('mp3-mode')
        setting_name = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }[mode]
    else:
        setting_name = {
            'audio/x-vorbis': 'vorbis-quality',
            'audio/x-m4a': 'aac-quality',
            'audio/ogg; codecs=opus': 'opus-bitrate',
            'audio/x-flac': 'flac-compression',
            'audio/x-wav': 'wav-sample-width'
        }[mime_type]
    return setting_name


def get_bitrate_from_settings():
    """Get a human readable bitrate from quality settings.

    For example '~224 kbps'
    """
    settings = get_gio_settings()
    mime_type = settings.get_string('output-mime-type')
    mode = settings.get_string('mp3-mode')

    bitrate = 0
    approx = True

    if mime_type == 'audio/x-vorbis':
        quality = max(0, min(1, settings.get_double('vorbis-quality'))) * 10
        quality = round(quality)
        bitrates = (64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 500)
        bitrate = bitrates[quality]

    elif mime_type == 'audio/x-m4a':
        bitrate = settings.get_int('aac-quality')

    elif mime_type == 'audio/ogg; codecs=opus':
        bitrate = settings.get_int('opus-bitrate')

    elif mime_type == 'audio/mpeg':
        mp3_quality_setting_name = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }[mode]
        setting = settings.get_int(mp3_quality_setting_name)
        if mode == 'vbr':
            # depends on the input audio
            return 'N/A'
        if mode == 'cbr':
            approx = False
            bitrate = setting
        if mode == 'abr':
            bitrate = setting

    elif mime_type == 'audio/x-wav':
        approx = False
        output_resample = settings.get_boolean('output-resample')
        resample_rate = settings.get_int('resample-rate')
        sample_width = settings.get_int('wav-sample-width')
        if output_resample:
            bitrate = sample_width * resample_rate / 1000
        else:
            # the actual bitrate will depend on the input audio, which
            # cannot be known in the settings menu beforehand. Assume 44100
            # which is the most common.
            bitrate = sample_width * 44100 / 1000

    if bitrate:
        if approx:
            return '~{} kbps'.format(bitrate)
        else:
            return '{} kbps'.format(bitrate)
    else:
        return 'N/A'


def get_default_quality(mime, mode='vbr'):
    """Return a default quality if the -q parameter is not set.

    Parameters
    ----------
    mime : string
        mime type
    mode : string
        one of 'cbr', 'abr' and 'vbr' for mp3
    """
    # get 6-tuple of qualities
    default = {
        'audio/x-vorbis': 1.0,
        'audio/x-m4a': 400,
        'audio/ogg; codecs=opus': 192,
        'audio/mpeg': {
            'cbr': 320,
            'abr': 320,
            'vbr': 0,  # inverted !
        },
        'audio/x-wav': 16,
        'audio/x-flac': 5
    }[mime]

    if isinstance(default, dict):
        default = default[mode]

    return default


def get_quality(mime, value, mode='vbr', reverse=False):
    """Map an integer between 0 and 5 to a proper quality/compression value.

    Parameters
    ----------
    mime : string
        mime type
    value : number
        between 0 and 5, or 0 and 2 for flac and wav. -1 indexes the highest
        quality.
    mode : string
        one of 'cbr', 'abr' and 'vbr' for mp3
    reverse : bool
        default False. If True, this function returns the original
        value-parameter given a quality setting. Value becomes the input for
        the quality then.
    """

    # get 6-tuple of qualities
    qualities = {
        'audio/x-vorbis': (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        'audio/x-m4a': (64, 96, 128, 192, 256, 320),
        'audio/ogg; codecs=opus': (48, 64, 96, 128, 160, 192),
        'audio/mpeg': {
            'cbr': (64, 96, 128, 192, 256, 320),
            'abr': (64, 96, 128, 192, 256, 320),
            'vbr': (9, 7, 5, 3, 1, 0),  # inverted !
        },
        'audio/x-wav': (8, 16, 32),
        'audio/x-flac': (0, 5, 8)
    }[mime]

    if isinstance(qualities, dict):
        qualities = qualities[mode]

    # return depending on function parameters
    if reverse:
        if isinstance(value, float):
            # floats are inaccurate, search for close value
            for i, quality in enumerate(qualities):
                if abs(value - quality) < 0.01:
                    return i
        if value in qualities:
            return qualities.index(value)
        else:
            # might be some custom value set e.g. in batch mode.
            # the reverse mode is only interesting for the ui though, because
            # it has predefined qualities as opposed to batch. So this is
            # either a setting leaking from some tests or the batch mode
            # persisted something.
            if mime == 'mp3':
                ftype_mode = '{} {}'.format(mime, mode)
            else:
                ftype_mode = mime
            logger.warning(
                'tried to index unknow {} quality {}'.format(ftype_mode, value)
            )
            return None
    else:
        # normal index
        if value > len(qualities):
            raise ValueError('quality index {} has to be < {}'.format(
                value, len(qualities)
            ))
        return qualities[value]
