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

from gettext import gettext as _
import sys


class SoundConverterException(Exception):

    def __init__(self, primary, secondary):
        Exception.__init__(self)
        self.primary = primary
        self.secondary = secondary


class ConversionTargetExists(SoundConverterException):

    def __init__(self, uri):
        SoundConverterException.__init__(self, _('Target exists.'),
                            (_('The output file %s already exists.')) % uri)


class NoLink(SoundConverterException):

    def __init__(self):
        SoundConverterException.__init__(self, _('Internal error'),
                _('Couldn\'t link GStreamer elements.\n '
                    'Please report this as a bug.'))


class UnknownType(SoundConverterException):

    def __init__(self, uri, mime_type):
        SoundConverterException.__init__(self,
                _('Unknown type %s') % mime_type,
                (_('The file %s is of an unknown type.\n '
                    'Please ask the developers to add support\n '
                    'for files of this type if it is important\n to you.'))
                    % uri)


class ErrorPrinter:

    def show_error(self, primary, secondary):
        sys.stderr.write(_('\n\nError: %s\n%s\n') % (primary, secondary))
        sys.exit(1)

    def show_exception(self, e):
        self.show(e.primary, e.secondary)


error_handler = ErrorPrinter()

def set_error_handler(handler):
    global error_handler
    error_handler = handler

def show_error(primary, secondary):
    error_handler.show_error(primary, secondary)

def show_exception(e):
    error_handler.show_exception(e)


