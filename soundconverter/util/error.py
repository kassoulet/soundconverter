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


from soundconverter.util.logger import logger


class ErrorPrinter:
    """Default error handler"""

    def show_error(self, primary, secondary=None):
        if secondary:
            logger.error(f"{primary}: {secondary}")
        else:
            logger.error(primary)
        pass


error_handler = ErrorPrinter()


def set_error_handler(handler):
    """Add a function to show errors on the UI."""
    global error_handler
    error_handler = handler


def show_error(primary, secondary=None):
    error_handler.show_error(primary, secondary)
