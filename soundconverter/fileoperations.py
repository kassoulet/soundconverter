#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2012 Gautier Portet
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
import urllib.request, urllib.parse, urllib.error
import gi
from gi.repository import GObject, Gio

from soundconverter.utils import log
from soundconverter.error import show_error

use_gnomevfs = False

def unquote_filename(filename):
    return urllib.parse.unquote(filename)


def beautify_uri(uri):
    return unquote_filename(uri).split('file://')[-1]


def vfs_walk(uri):
    """similar to os.path.walk, but with Gio.

    uri -- the base folder uri.
    return a list of uri.

    """
    filelist = []

    dirlist = Gio.file_parse_name(uri).enumerate_children('*', Gio.FileMonitorFlags.NONE, None)
    print(dirlist)
    for file_info in dirlist:
        name = file_info.get_name()
        print(name)
        info = dirlist.get_child(file_info).query_file_type(Gio.FileMonitorFlags.NONE, None)
        if info == Gio.FileType.DIRECTORY:
            filelist.extend(vfs_walk(uri + '/' + name))
        if info == Gio.FileType.REGULAR:
            filelist.append(str(uri + '/' + name))
    return filelist


def vfs_makedirs(path_to_create):
    """Similar to os.makedirs, but with gnomevfs."""

    uri = gnomevfs.URI(path_to_create)
    path = uri.path

    # start at root
    uri = uri.resolve_relative('/')

    for folder in path.split('/'):
        if not folder:
            continue
        uri = uri.append_string(folder.replace('%2f', '/'))
        try:
            gnomevfs.make_directory(uri, 0o777)
        except gnomevfs.FileExistsError:
            pass
        except:
            return False
    return True


def vfs_unlink(filename):
    """Delete a gnomevfs file."""
    
    gnomevfs.unlink(gnomevfs.URI(filename))


def vfs_rename(original, newname):
    """Rename a gnomevfs file"""
    
    uri = gnomevfs.URI(newname)
    dirname = uri.parent
    if dirname and not gnomevfs.exists(dirname):
        log('Creating folder: \'%s\'' % dirname)
        if not vfs_makedirs(str(dirname)):
            show_error(_('Cannot create folder!'), unquote_filename(dirname.path))
            return 'cannot-create-folder'

    try:
        gnomevfs.xfer_uri(gnomevfs.URI(original), uri,
                          gnomevfs.XFER_REMOVESOURCE,
                          gnomevfs.XFER_ERROR_MODE_ABORT,
                          gnomevfs.XFER_OVERWRITE_MODE_ABORT
                         )
    except Exception as error:
        # TODO: maybe we need a special case here. If dest folder is unwritable. Just stop.
        # or an option to stop all processing.
        show_error(_('Error while renaming file!'), '%s: %s' % (beautify_uri(newname), error))
        return 'cannot-rename-file'


def vfs_exists(filename):
    try:
        return gnomevfs.exists(filename)
    except:
        return False


def filename_to_uri(filename):
    """Convert a filename to a valid uri.
    Filename can be a relative or absolute path, or an uri.
    """
    if '://' not in filename:
        # convert local filename to uri
        filename = 'file://' + urllib.request.pathname2url(os.path.abspath(filename))
    filename = Gio.file_parse_name(filename).get_uri()
    return filename


# GStreamer gnomevfssrc helpers

def vfs_encode_filename(filename):
    return filename_to_uri(filename)


def file_encode_filename(filename):
    return Gio.get_local_path_from_uri(filename).replace(' ', '\ ')
    
