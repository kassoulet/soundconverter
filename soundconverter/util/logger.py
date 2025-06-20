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

# logging & debugging

from soundconverter.util.settings import settings
import logging


class Formatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO and not settings["debug"]:
            # if not launched with --debug, then don't print "INFO:"
            self._style._fmt = "%(msg)s"  # noqa
        else:
            # see https://en.wikipedia.org/wiki/ANSI_escape_code#3/4_bit
            # for those numbers
            color = {
                logging.WARNING: 33,
                logging.ERROR: 31,
                logging.FATAL: 31,
                logging.DEBUG: 36,
                logging.INFO: 32,
            }.get(record.levelno, 0)
            if settings["debug"]:
                self._style._fmt = (  # noqa
                    "\033[{}m%(levelname)s\033[0m: "
                    "%(filename)s, line %(lineno)d, %(message)s"
                ).format(color)
            else:
                self._style._fmt = (  # noqa
                    "\033[{}m%(levelname)s\033[0m: %(message)s"
                ).format(color)
        return super().format(record)


logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(Formatter())
logger.addHandler(handler)


def update_verbosity():
    """Set the logging verbosity according to the settings object."""
    if settings["debug"]:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
