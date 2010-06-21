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

import gconf


class GConfStore(object):

    def __init__(self, root, defaults):
        self.gconf = gconf.client_get_default()
        self.gconf.add_dir(root, gconf.CLIENT_PRELOAD_ONELEVEL)
        self.root = root
        self.defaults = defaults

    def get_with_default(self, getter, key):
        if self.gconf.get(self.path(key)) is None:
            return self.defaults[key]
        else:
            return getter(self.path(key))

    def get_int(self, key):
        return self.get_with_default(self.gconf.get_int, key)

    def set_int(self, key, value):
        self.gconf.set_int(self.path(key), value)

    def get_float(self, key):
        return self.get_with_default(self.gconf.get_float, key)

    def set_float(self, key, value):
        self.gconf.set_float(self.path(key), value)

    def get_string(self, key):
        return self.get_with_default(self.gconf.get_string, key)

    def set_string(self, key, value):
        self.gconf.set_string(self.path(key), value)

    def path(self, key):
        assert key in self.defaults, 'missing gconf default:%s' % key
        return '%s/%s' % (self.root, key)
