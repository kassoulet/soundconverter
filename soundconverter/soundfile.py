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

import os
import gobject

from fileoperations import unquote_filename


class SoundFile:

    """Meta data information about a sound file (uri, tags)."""

    def __init__(self, uri, base_path=None):

        self.uri = uri

        if base_path:
            self.base_path = base_path
            self.filename = self.uri[len(self.base_path):]
        else:
            self.base_path, self.filename = os.path.split(self.uri)
            self.base_path += '/'

        self.tags = {
            'track-number': 0,
            'title':  'Unknown Title',
            'artist': 'Unknown Artist',
            'album':  'Unknown Album',
        }
        self.have_tags = False
        self.tags_read = False
        self.duration = 0
        self.mime_type = None

    def get_uri(self):
        return self.uri

    def get_base_path(self):
        return self.base_path

    def get_filename(self):
        return self.filename

    def get_filename_for_display(self):
        return gobject.filename_display_name(
                unquote_filename(self.filename))

    def add_tags(self, taglist):
        for key in taglist.keys():
            self.tags[key] = taglist[key]

    def get_tag_names(self):
        return self.tags.keys()

    def get_tag(self, key, default=''):
        return self.tags.get(key, default)

    get = get_tag
    __getitem__ = get_tag

    def keys(self):
        return self.tags.keys()
