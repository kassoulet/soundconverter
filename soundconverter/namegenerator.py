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

import string
import time
import os
import urllib
import unicodedata
import gnomevfs
from fileoperations import vfs_exists

class TargetNameGenerator:

    """Generator for creating the target name from an input name."""

    nice_chars = string.ascii_letters + string.digits + '.-_/'

    def __init__(self):
        self.folder = None
        self.subfolders = ''
        self.basename = '%(.inputname)s'
        self.ext = '%(.ext)s'
        self.suffix = None
        self.replace_messy_chars = False
        self.max_tries = 2
        self.exists = vfs_exists

    def _unicode_to_ascii(self, unicode_string):
        # thanks to
        # http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/251871
        try:
            unicode_string = unicode(unicode_string, 'utf-8')
            return unicodedata.normalize('NFKD', unicode_string).encode(
                                                            'ASCII', 'ignore')
        except UnicodeDecodeError:
            unicode_string = unicode(unicode_string, 'iso-8859-1')
            return unicodedata.normalize('NFKD', unicode_string).encode(
                                                            'ASCII', 'replace')

    def get_target_name(self, sound_file):

        assert self.suffix, 'you just forgot to call set_target_suffix()'

        u = gnomevfs.URI(sound_file.uri)
        root, ext = os.path.splitext(u.path)

        root = sound_file.base_path
        basename, ext = os.path.splitext(urllib.unquote(sound_file.filename))

        # make sure basename constains only the filename
        basefolder, basename = os.path.split(basename)

        d = {
            '.inputname': basename,
            '.ext': ext,
            'album': 'Unknown Album',
            'artist': 'Unknown Artist',
            'title': 'Unknown Title',
            'track-number': 0,
            'track-count': 0,
            'genre': '',
            'year': '',
            'date': '',
            'disc-number': 0,
            'disc-count': 0,
        }
        for key in sound_file.tags:
            d[key] = sound_file.tags[key]
            if isinstance(d[key], basestring):
                # take care of tags containing slashes
                d[key] = d[key].replace('/', '-')

        # add timestamp to substitution dict -- this could be split into more
        # entries for more fine-grained control over the string by the user...
        timestamp_string = time.strftime('%Y%m%d_%H_%M_%S')
        d['timestamp'] = timestamp_string

        pattern = os.path.join(self.subfolders, self.basename + self.suffix)
        result = pattern % d
        if isinstance(result, unicode):
            result = result.encode('utf-8')

        if self.replace_messy_chars:
            result = self._unicode_to_ascii(result)
            s = ''
            for c in result:
                if c not in self.nice_chars:
                    s += '_'
                else:
                    s += c
            result = s

        #print 'folder:', self.folder
        #print 'root:', root
        #print 'basefolder:', basefolder
        #print 'result:', result
        if self.folder is None:
            folder = root
        else:
            folder = urllib.quote(self.folder, '/:')

        result = os.path.join(folder, basefolder, urllib.quote(result))

        return result
