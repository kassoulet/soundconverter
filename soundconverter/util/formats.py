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

import math
from gettext import gettext as _

from soundconverter.util.settings import get_gio_settings
from soundconverter.gstreamer.profiles import audio_profiles_dict

# add here any format you want to be read
mime_whitelist = (
    'audio/',
    'video/',
    'application/ogg',
    'application/x-id3',
    'application/x-ape',
    'application/vnd.rn-realmedia',
    'application/x-pn-realaudio',
    'application/x-shockwave-flash',
    'application/x-3gp',
)

filename_blacklist = (
    '*.iso',
)

# custom filename patterns
english_patterns = 'Artist Album Album-Artist Title Track Total Genre Date ' \
                   'Year Timestamp DiscNumber DiscTotal Ext'

# traductors: These are the custom filename patterns. Only if it makes sense.
locale_patterns = _('Artist Album Album-Artist Title Track Total Genre Date '
                    'Year Timestamp DiscNumber DiscTotal Ext')

patterns_formats = (
    '%(artist)s',
    '%(album)s',
    '%(album-artist)s',
    '%(title)s',
    '%(track-number)02d',
    '%(track-count)02d',
    '%(genre)s',
    '%(date)s',
    '%(year)s',
    '%(timestamp)s',
    '%(album-disc-number)d',
    '%(album-disc-count)d',
    '%(.target-ext)s',
)

# add english and locale
custom_patterns = english_patterns + ' ' + locale_patterns
# convert to list
custom_patterns = ['{%s}' % p for p in custom_patterns.split()]
# and finally to dict, thus removing doubles
custom_patterns = dict(list(zip(custom_patterns, patterns_formats * 2)))

locale_patterns_dict = dict(list(zip(
    [p.lower() for p in english_patterns.split()],
    ['{%s}' % p for p in locale_patterns.split()])))

# Name and pattern for CustomFileChooser
filepattern = (
    (_('All files'), '*.*'),
    ('MP3', '*.mp3'),
    ('Ogg Vorbis', '*.ogg;*.oga'),
    ('iTunes AAC ', '*.m4a'),
    ('Windows WAV', '*.wav'),
    ('AAC', '*.aac'),
    ('FLAC', '*.flac'),
    ('AC3', '*.ac3')
)


def get_mime_type_mapping():
    """Return a mapping of file extension to mime type."""
    profile = get_gio_settings().get_string('audio-profile')
    mime_types = {
        'ogg': 'audio/x-vorbis', 'flac': 'audio/x-flac', 'wav': 'audio/x-wav',
        'mp3': 'audio/mpeg', 'aac': 'audio/x-m4a', 'm4a': 'audio/x-m4a'
    }
    if profile in audio_profiles_dict:
        profile_ext = audio_profiles_dict[profile][1] if profile else ''
        mime_types[profile_ext] = 'gst-profile'
    return mime_types


def get_mime_type(t):
    """Return the matching mime-type or None if it is not supported.

    Parameters
    ----------
    t : string
        extension (like 'mp3')
    """
    mime_types = get_mime_type_mapping()
    if t not in mime_types.values():
        # possibly a file extension
        return mime_types.get(t, None)
    else:
        # already a mime string
        return t


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
    """Depending on the selected mime_type, get the gio settings name."""
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
            # TODO check which values would be correct here
            bitrates = (320, 256, 224, 192, 160, 128)
            bitrate = bitrates[setting]
        if mode == 'cbr':
            approx = False
            bitrate = setting
        if mode == 'abr':
            bitrate = setting

    if bitrate:
        if approx:
            return '~{} kbps'.format(bitrate)
        else:
            return '{} kbps'.format(bitrate)
    else:
        return 'N/A'


def get_quality(ftype, value, mode='vbr', reverse=False):
    """Map an integer between 0 and 5 to a proper quality/compression value.

    Parameters
    ----------
    ftype : string
        'ogg', 'aac', 'opus', 'flac', 'wav' or 'mp3'
    value : number
        between 0 and 5, or 0 and 2 for flac and wav
    mode : string
        one of 'cbr', 'abr' and 'vbr' for mp3
    reverse : boolean
        default False. If True, this function returns the original
        value-parameter given a quality setting. Value becomes the input for
        the quality then.
    """
    quality = {
        'ogg': (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        'aac': (64, 96, 128, 192, 256, 320),
        'opus': (48, 64, 96, 128, 160, 192),
        'mp3': {
            'cbr': (64, 96, 128, 192, 256, 320),
            'abr': (64, 96, 128, 192, 256, 320),
            'vbr': (9, 7, 5, 3, 1, 0),  # inverted !
        },
        'wav': (8, 16, 32),
        'flac': (0, 5, 8)
    }

    # get 6-tuple of qualities
    if ftype == 'mp3':
        qualities = quality[ftype][mode]
    else:
        qualities = quality[ftype]

    # return depending on function parameters
    if reverse:
        if type(value) == float:
            # floats are inaccurate, search for close value
            for i, q in enumerate(qualities):
                if abs(value - q) < 0.01:
                    return i
        return qualities.index(value)
    else:
        # normal index
        if value > len(qualities) or value < 0:
            raise ValueError('quality index {} out of range 0 - {}'.format(
                value, len(qualities)
            ))
        return qualities[value]
