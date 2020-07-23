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

from gettext import gettext as _

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
english_patterns = 'Artist Album Album-Artist Title Track Total Genre Date Year Timestamp DiscNumber DiscTotal Ext'

# traductors: These are the custom filename patterns. Only if it makes sense.
locale_patterns = _('Artist Album Album-Artist Title Track Total Genre Date Year Timestamp DiscNumber DiscTotal Ext')

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
    ('MP3',          '*.mp3'),
    ('Ogg Vorbis',   '*.ogg;*.oga'),
    ('iTunes AAC ',  '*.m4a'),
    ('Windows WAV',  '*.wav'),
    ('AAC',          '*.aac'),
    ('FLAC',         '*.flac'),
    ('AC3',          '*.ac3')
)


mime_types = {
    'vorbis': 'audio/x-vorbis', 'flac': 'audio/x-flac', 'wav': 'audio/x-wav',
    'mp3': 'audio/mpeg', 'aac': 'audio/x-m4a'
}


def get_mime_type(t):
    """Return the matching mime-type or None if it is not supported.
    
    Parameters
    ----------
        t : string
            extension-type (like 'mp3') or mime-type (like 'audio/x-m4a')
    """
    if t not in mime_types.values():
        # possibly a file extension
        return mime_types.get(t, None)
    else:
        # already a mime string
        return t


def get_quality(ftype, value, mode='vbr', reverse=False):
    """Map an integer between 0 and 6 to a proper quality value depending on target file type.

    Parameters
    ----------
        ftype : string
            'vorbis', 'aac', 'opus' or 'mp3',
        value : number
            between 0 and 5,
        mode : string
            one of 'cbr', 'abr' and 'vbr' for mp3
        reverse : boolean
            default False. If True, this function returns the original value-parameter
            given a quality setting. Value becomes the input for the quality then.
    """
    quality = {
        'vorbis': (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        'aac': (64, 96, 128, 192, 256, 320),
        'opus': (48, 64, 96, 128, 160, 192),
        'mp3': {
            'cbr': (64, 96, 128, 192, 256, 320),
            'abr': (64, 96, 128, 192, 256, 320),
            'vbr': (9, 7, 5, 3, 1, 0),  # inverted !
        }
    }

    # get 6-tuple of qualities
    qualities = None
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
        return qualities[value]
