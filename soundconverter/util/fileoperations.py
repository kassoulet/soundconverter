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

import os
import re
import urllib.request
import urllib.parse
import urllib.error
from gi.repository import Gio

from soundconverter.util.logger import logger


def unquote_filename(filename):
    """Transform an URL encoded filename to a non-encoded one.

    E.g. '%20' will be changed to ' '
    """
    return urllib.parse.unquote(str(filename))


def beautify_uri(uri):
    """Convert an URI to a normal path.

    Also returns the prefix, for example 'file://'"""
    match = split_uri(uri)
    if match[0] is not None:
        # take the path part from the uri
        path = match[1]
        path = unquote_filename(path)
    else:
        # no uri, take as is, return any existing %20 strings without
        # modifying them.
        path = uri
    return path


def vfs_walk(uri):
    """Similar to os.path.walk, but with Gio.

    uri -- the base folder uri.
    return a list of uri.
    """
    filelist = []

    try:
        dirlist = Gio.file_parse_name(uri).enumerate_children(
            '*', Gio.FileMonitorFlags.NONE, None
        )

        for file_info in dirlist:
            info = dirlist.get_child(file_info).query_file_type(
                Gio.FileMonitorFlags.NONE, None
            )

            uri = dirlist.get_child(file_info).get_uri();

            if info == Gio.FileType.DIRECTORY:
                filelist.extend(vfs_walk(uri))

            if info == Gio.FileType.REGULAR:
                filelist.append(str(uri))
    except Exception as e:
        # this is impossible to write unittests for, because this only happens
        # when the owner of this directory is e.g. root
        logger.error('Failed to walk "%s": "%s"', uri, e)

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
    if not gfnew.get_parent().query_exists(None):
        fgnew_uri = gfnew.get_parent().get_uri()
        logger.debug('Creating folder: \'{}\''.format(fgnew_uri))
        Gio.File.make_directory_with_parents(gfnew.get_parent(), None)
    gforiginal.move(gfnew, Gio.FileCopyFlags.NONE, None, None, None)


def vfs_exists(filename):
    """Check if file or URI exists."""
    if not is_uri(filename):
        # gio does not support relative path syntax
        filename = os.path.realpath(filename)
    gfile = Gio.file_parse_name(filename)
    return gfile.query_exists(None)


def split_uri(uri):
    """Match a regex to the uri that results in:

    [0]: scheme and authority, might be None if not an uri
    [1]: filename. This still has to be unquoted!
    """
    if not isinstance(uri, str):
        raise ValueError('cannot split {} {}'.format(type(uri), uri))

    match = re.match(r'^([a-zA-Z]+://([^/]+?)?)?(/.*)', uri)
    if match is None:
        # not an uri
        return None, uri
    return match[1], match[3]


def is_uri(uri):
    return split_uri(uri)[0] is not None


def filename_to_uri(filename, prefix='file://'):
    """Convert a filename to a valid uri.

    Parameters
    ----------
    filename : string
        Filename can be a relative or absolute path, or an URI. If an URI,
        only characters that are not escaped yet will be escaped.
    prefix : string
        for example 'file://'
    """
    match = split_uri(filename)
    if match[0]:
        # it's an URI! It can be basically just returned as is. But to make
        # sure that all characters are URI escaped, the path will be
        # escaped again. Don't quote the schema.
        # e.g. a pattern contained file:// in front but inserting tags into it
        # resulted in whitespaces.
        # ' %20' to '  ' to '%20%20'. Don't quote it to '%20%2520'!
        filename = unquote_filename(match[1])
        filename = urllib.parse.quote(filename)
        uri = match[0] + filename
    else:
        # convert to absolute path
        filename = os.path.realpath(filename)
        # it's a normal path. If it happens to contain %25, it might be
        # part of the album name or something. ' %20' should become '%20%2520'
        uri = prefix + urllib.parse.quote(filename)
    return uri


# GStreamer gnomevfssrc helpers


def vfs_encode_filename(filename):
    return filename_to_uri(filename)


def file_encode_filename(filename):
    return Gio.get_local_path_from_uri(filename).replace(' ', r'\ ')
