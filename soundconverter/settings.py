#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2010 Gautier Portet
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

# custom filename patterns
english_patterns = 'Artist Album Title Track Total Genre Date Year Timestamp'

# traductors: These are the custom filename patterns. Only if it makes sense.
locale_patterns = _('Artist Album Title Track Total Genre Date Year Timestamp')

patterns_formats = (
    '%(artist)s',
    '%(album)s',
    '%(title)s',
    '%(track-number)02d',
    '%(track-count)02d',
    '%(genre)s',
    '%(date)s',
    '%(year)s',
    '%(timestamp)s',
)

# add english and locale
custom_patterns = english_patterns + ' ' + locale_patterns
# convert to list
custom_patterns = ['{%s}' % p for p in custom_patterns.split()]
# and finally to dict, thus removing doubles
custom_patterns = dict(zip(custom_patterns, patterns_formats * 2))

locale_patterns_dict = dict(zip(
    [p.lower() for p in english_patterns.split()],
    ['{%s}' % p for p in locale_patterns.split()]))

# add here the formats not containing tags
# not to bother searching in them
tag_blacklist = (
    'audio/x-wav',
)


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


def cpu_count():
    '''
    Returns the number of CPUs in the system.
    (from pyprocessing)
    '''
    import sys
    import os
    if sys.platform == 'win32':
        try:
            num = int(os.environ['NUMBER_OF_PROCESSORS'])
        except (ValueError, KeyError):
            num = 0
    elif sys.platform == 'darwin':
        try:
            num = int(os.popen('sysctl -n hw.ncpu').read())
        except ValueError:
            num = 0
    else:
        try:
            num = os.sysconf('SC_NPROCESSORS_ONLN')
        except (ValueError, OSError, AttributeError):
            num = 0
    if num >= 1:
        return num
    else:
        return 1

# application-wide settings
settings = {
    'mode': 'gui',
    'quiet': False,
    'debug': False,
    'cli-output-type': 'audio/x-vorbis',
    'cli-output-suffix': '.ogg',
    'jobs': cpu_count(),
}
