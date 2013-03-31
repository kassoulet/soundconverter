#!/usr/bin/python
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
import urllib
import urlparse
import gnomevfs

from utils import log
from error import show_error

use_gnomevfs = False

def unquote_filename(filename):
    return urllib.unquote(filename)


def beautify_uri(uri):
    return unquote_filename(uri).split('file://')[-1]


def vfs_walk(uri):
    """similar to os.path.walk, but with gnomevfs.

    uri -- the base folder uri.
    return a list of uri.

    """
    if str(uri)[-1] != '/':
        uri = uri.append_string('/')

    filelist = []

    try:
        dirlist = gnomevfs.open_directory(uri, gnomevfs.FILE_INFO_FOLLOW_LINKS)
    except:
        log("skipping: '%s\'" % uri)
        return filelist

    for file_info in dirlist:
        try:
            if file_info.name[0] == '.':
                continue

            if file_info.type == gnomevfs.FILE_TYPE_DIRECTORY:
                filelist.extend(
                    vfs_walk(uri.append_path(file_info.name)))

            if file_info.type == gnomevfs.FILE_TYPE_REGULAR:
                filelist.append(str(uri.append_file_name(file_info.name)))
        except ValueError:
            # this can happen when you do not have sufficent
            # permissions to read file info.
            log("skipping: \'%s\'" % uri)
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
            gnomevfs.make_directory(uri, 0777)
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
            return

    try:
        gnomevfs.xfer_uri(gnomevfs.URI(original), uri,
                          gnomevfs.XFER_REMOVESOURCE,
                          gnomevfs.XFER_ERROR_MODE_ABORT,
                          gnomevfs.XFER_OVERWRITE_MODE_ABORT
                         )
    except Exception as error:
        show_error(_('Error while renaming file!'), '%s: %s' % (beautify_uri(newname), error))
        


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
        filename = urllib.pathname2url(os.path.abspath(filename))
    filename = str(gnomevfs.URI(filename))
    return filename


# GStreamer gnomevfssrc helpers

def vfs_encode_filename(filename):
    return filename_to_uri(filename)


def file_encode_filename(filename):
    return gnomevfs.get_local_path_from_uri(filename).replace(' ', '\ ')
    
