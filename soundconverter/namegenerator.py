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
        #if use_gnomevfs: TODO
        #   self.exists = gnomevfs.exists
        #else:
        #   self.exists = os.path.exists
        self.exists = os.path.exists

    # This is useful for unit testing.
    def set_exists(self, exists):
        self.exists = exists

    def set_target_suffix(self, suffix):
        self.suffix = suffix

    def set_folder(self, folder):
        self.folder = folder

    def set_subfolder_pattern(self, pattern):
        self.subfolders = pattern

    def set_basename_pattern(self, pattern):
        self.basename = pattern

    def set_replace_messy_chars(self, yes_or_no):
        self.replace_messy_chars = yes_or_no

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

        u = gnomevfs.URI(sound_file.get_uri())
        root, ext = os.path.splitext(u.path)
        if u.host_port:
            host = '%s:%s' % (u.host_name, u.host_port)
        else:
            host = u.host_name # TODO, where is host used ?

        root = sound_file.get_base_path()
        basename, ext = os.path.splitext(urllib.unquote(
                                            sound_file.get_filename()))

        # make sure basename constains only the filename
        basefolder, basename = os.path.split(basename)

        d = {
            '.inputname': basename,
            '.ext': ext,
            'album': '',
            'artist': '',
            'title': '',
            'track-number': 0,
            'track-count': 0,
            'genre': '',
            'year': '',
            'date': '',
        }
        for key in sound_file.keys():
            d[key] = sound_file[key]
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

        if self.folder is None:
            folder = root
        else:
            folder = urllib.quote(self.folder, '/:')

        result = os.path.join(folder, basefolder, urllib.quote(result))

        return result
