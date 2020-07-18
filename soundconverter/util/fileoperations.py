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

import os
import urllib.request
import urllib.parse
import urllib.error
import gi
from gi.repository import Gio

from soundconverter.util import logger
from soundconverter.util.error import show_error


def unquote_filename(filename):
    """Transform an URL encoded filename to a non-encoded one.

    E.g. '%20' will be changed to ' '
    """
    return urllib.parse.unquote(str(filename))


def beautify_uri(uri):
    return unquote_filename(uri).split('file://')[-1]


def vfs_walk(uri):
    """Similar to os.path.walk, but with Gio.

    uri -- the base folder uri.
    return a list of uri.

    """
    filelist = []
    dirlist = Gio.file_parse_name(uri).enumerate_children('*', Gio.FileMonitorFlags.NONE, None)
    for file_info in dirlist:
        name = file_info.get_name()
        info = dirlist.get_child(file_info).query_file_type(Gio.FileMonitorFlags.NONE, None)
        if info == Gio.FileType.DIRECTORY:
            filelist.extend(vfs_walk(dirlist.get_child(file_info).get_uri()))
        if info == Gio.FileType.REGULAR:
            filelist.append(str(dirlist.get_child(file_info).get_uri()))
    return filelist


def vfs_getparent(path):
    """Get folder name."""
    gfile = Gio.file_parse_name(path)
    return gfile.get_parent()


def vfs_unlink(filename):
    """Delete a gnomevfs file."""
    gfile = Gio.file_parse_name(filename)
    return gfile.delete(None)


def vfs_rename(original, newname):
    """Rename a gnomevfs file."""
    gforiginal = Gio.file_parse_name(original)
    gfnew = Gio.file_parse_name(newname)
    logger.debug('Creating folder \'{}\'?'.format(gfnew.get_parent().get_uri()))
    if not gfnew.get_parent().query_exists(None):
        logger.debug('Creating folder: \'{}\''.format(gfnew.get_parent().get_uri()))
        Gio.File.make_directory_with_parents(gfnew.get_parent(), None)
    gforiginal.move(gfnew, Gio.FileCopyFlags.NONE, None, None, None)


def vfs_exists(filename):
    gfile = Gio.file_parse_name(filename)
    return gfile.query_exists(None)


def filename_to_uri(filename):
    """Convert a filename to a valid uri.

    Filename can be a relative or absolute path, or an uri.
    """
    if '://' not in filename:
        # convert local filename to uri
        filename = 'file://' + os.path.abspath(filename)
        for char in '#', '%':
            filename = filename.replace(char, '%%%x' % ord(char))
    uri = Gio.file_parse_name(filename).get_uri()
    return uri


# GStreamer gnomevfssrc helpers

def vfs_encode_filename(filename):
    return filename_to_uri(filename)


def file_encode_filename(filename):
    return Gio.get_local_path_from_uri(filename).replace(' ', r'\ ')
