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

import string
import time
import re
import os
import urllib.request
import urllib.parse
import urllib.error
import unicodedata
from gettext import gettext as _
import gi
from gi.repository import Gio
from soundconverter.fileoperations import vfs_exists, filename_to_uri, unquote_filename


class TargetNameGenerator:
    """Generator for creating the target name from an input name."""

    def __init__(self):
        self.folder = None
        self.subfolders = ''
        self.basename = '%(.inputname)s'
        self.ext = '%(.ext)s'
        self.suffix = None
        self.replace_messy_chars = False
        self.max_tries = 2
        self.exists = vfs_exists

    @staticmethod
    def _unicode_to_ascii(unicode_string):
        # thanks to http://code.activestate.com/recipes/251871/
        return str(unicodedata.normalize('NFKD', unicode_string).encode('ASCII', 'ignore'), 'ASCII')

    @staticmethod
    def safe_name(filename):
        """Replace all characters that are not ascii, digits or '.' '-' '_' '/' with '_'.
        
        Will not be applied on the part of the path that already exists, as that part apparently is already safe

        Parameters
        ----------
        path : string
            Can be an URI or a normal path
        """
        if len(filename) == 0:
            raise ValueError('empty filename')

        nice_chars = string.ascii_letters + string.digits + '.-_/'

        scheme = ''
        # don't break 'file://' and keep the original scheme
        match = re.match(r'^([a-zA-Z]+://){0,1}(.+)', filename)
        if match[1]:
            # it's an URI!
            scheme = match[1]
            filename = match[2]
            filename = unquote_filename(filename)

        # figure out how much of the path already exists
        # split into for example [/test', '/baz.flac'] or ['qux.mp3']
        split = [s for s in re.split(r'((?:/|^)[^/]+)', filename) if s != '']
        safe = ''
        while len(split) > 0:
            part = split.pop(0)
            if os.path.exists(safe + part):
                safe += part
            else:
                # put the remaining unknown non-existing path back together and make it safe
                non_existing = TargetNameGenerator._unicode_to_ascii(part + ''.join(split))
                non_existing = ''.join([c if c in nice_chars else '_' for c in non_existing])
                safe += non_existing
                break

        if match[1]:
            safe = filename_to_uri(scheme + safe)

        return safe

    def get_target_name(self, sound_file):
        assert self.suffix, 'you just forgot to call set_target_suffix()'

        root, ext = os.path.splitext(urllib.parse.urlparse(sound_file.uri).path)

        root = sound_file.base_path
        basename, ext = os.path.splitext(
            urllib.parse.unquote(sound_file.filename))

        # make sure basename contains only the filename
        basefolder, basename = os.path.split(basename)

        d = {
            '.inputname': basename,
            '.ext': ext,
            '.target-ext': self.suffix[1:],
            'album': _('Unknown Album'),
            'artist': _('Unknown Artist'),
            'album-artist': _('Unknown Artist'),
            'title': basename,
            'track-number': 0,
            'track-count': 0,
            'genre': '',
            'year': '',
            'date': '',
            'album-disc-number': 0,
            'album-disc-count': 0,
        }
        for key in sound_file.tags:
            d[key] = sound_file.tags[key]
            if isinstance(d[key], str):
                # take care of tags containing slashes
                d[key] = d[key].replace('/', '-')
                if key.endswith('-number'):
                    d[key] = int(d[key])
        # when artist set & album-artist not, use artist for album-artist
        if 'artist' in sound_file.tags and 'album-artist' not in sound_file.tags:
            d['album-artist'] = sound_file.tags['artist']

        # add timestamp to substitution dict -- this could be split into more
        # entries for more fine-grained control over the string by the user...
        timestamp_string = time.strftime('%Y%m%d_%H_%M_%S')
        d['timestamp'] = timestamp_string

        pattern = os.path.join(self.subfolders, self.basename + self.suffix)
        result = pattern % d

        if self.replace_messy_chars:
            result = self.safe_name(result)

        if self.folder is None:
            folder = root
        else:
            folder = urllib.parse.quote(self.folder, safe='/:%@')

        if '/' in pattern:
            # we are creating folders using tags, disable basefolder handling
            basefolder = ''

        result = os.path.join(folder, basefolder, urllib.parse.quote(result))

        return result
