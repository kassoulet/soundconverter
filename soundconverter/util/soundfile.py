#!/usr/bin/python3
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

import os

from gi.repository import GLib

from soundconverter.util.fileoperations import is_uri, unquote_filename


class SoundFile:
    """Meta data information about a sound file (uri, tags)."""

    __slots__ = [
        "uri",
        "base_path",
        "filename",
        "tags",
        "filelist_row",
        "subfolders",
        "readable",
        "duration",
        "info",
    ]

    def __init__(self, uri, base_path=None):
        """Create a SoundFile object.

        if base_path is set, the uri is cut in three parts,
         - the base folder, which is a common folder of multiple soundfiles
           (.base_path)
         - the remaining subfolders, which would be for example something
           like artist/album in the existing folder structure. As long as
           no subfolder pattern is provided, soundconverter will use those
           subfolders in the output directory. (in .subfolders)
         - the filename (in .filename)
        """
        # enforcing an uri format reduced the nightmare of handling 2
        # different path formats in generate_target_uri
        if not is_uri(uri):
            raise ValueError(f"uri was not an uri: {uri}!")
        if base_path is not None and not is_uri(base_path):
            raise ValueError(f"base_path was not an uri: {base_path}!")

        self.uri = uri
        self.subfolders = None

        if base_path:
            if not uri.startswith(base_path):
                raise ValueError(
                    f"uri {uri} needs to start with the base_path {base_path}!",
                )
            self.base_path = base_path
            subfolders, filename = os.path.split(uri[len(base_path) :])
            self.subfolders = unquote_filename(subfolders)
            self.filename = filename
        else:
            self.base_path, self.filename = os.path.split(self.uri)
            self.base_path += "/"

        self.filelist_row = None

        # properties of valid audio are yet to be figured out in a Discoverer
        self.tags = {}
        self.readable = False
        self.duration = None
        self.info = None

    @property
    def filename_for_display(self):
        """Return the filename in a form suitable for displaying it."""
        return GLib.filename_display_name(unquote_filename(self.filename))
