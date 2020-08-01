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

from gi.repository import Gst, GObject, GstPbutils

from soundconverter.util.task import Task

type_getters = {
    GObject.TYPE_STRING: 'get_string',
    GObject.TYPE_DOUBLE: 'get_double',
    GObject.TYPE_FLOAT: 'get_float',
    GObject.TYPE_INT: 'get_int',
    GObject.TYPE_UINT: 'get_uint',
}


class Discoverer(Task):
    """Find type and tags of a SoundFile if possible."""

    def __init__(self, sound_file):
        """Find type and tags of a SoundFile if possible."""
        self.sound_file = sound_file
        self.readable = None
        self.tags = None
        self.error = None

    def get_progress(self):
        """Fraction of how much of the task is completed."""
        # fast task, don't care
        return 1

    def cancel(self):
        """Cancel execution of the task."""
        # fast task, don't care
        pass

    def pause(self):
        """Pause execution of the task."""
        # fast task, don't care
        pass

    def resume(self):
        """Resume execution of the task."""
        # fast task, don't care
        pass

    def run(self):
        discoverer = GstPbutils.Discoverer()
        discoverer.connect('discovered', self._discovered)
        discoverer.start()
        discoverer.discover_uri_async(self.sound_file.uri)

    def _discovered(self, _, info, error):
        """The uri has been processed."""
        self.error = error
        if error is None:
            taglist = info.get_tags()
            taglist.foreach(self._add_tag)
            self.tags = info.get_tags()
            self.readable = True
            self.callback()
        else:
            self.readable = False
            self.callback()

    def _add_tag(self, taglist, tag):
        """Convert the taglist to a dict one by one."""
        tag_type = Gst.tag_get_type(tag)

        if tag_type in type_getters:
            getter = getattr(taglist, type_getters[tag_type])
            value = str(getter(tag)[1])
            self.sound_file.tags[tag] = value

        if 'datetime' in tag:
            dt = taglist.get_date_time(tag)[1]
            self.sound_file.tags['year'] = dt.get_year()
            self.sound_file.tags['date'] = dt.to_iso8601_string()[:10]
