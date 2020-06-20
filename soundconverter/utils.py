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

# logging & debugging

from .settings import settings
from gi.repository import GLib
import logging


class Formatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            self._style._fmt = '%(msg)s'
        else:
            # see https://en.wikipedia.org/wiki/ANSI_escape_code#3/4_bit for those numbers
            color = {
                logging.WARNING: 33,
                logging.ERROR: 31,
                logging.DEBUG: 36
            }[record.levelno]
            self._style._fmt = '\033[{}m%(levelname)s\033[0m: %(msg)s'.format(color)
        return super().format(record)


logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(Formatter())
logger.addHandler(handler)


def update_verbosity():
    """Set the logging verbosity according to the settings object."""
    if settings['debug']:
        logger.setLevel(logging.DEBUG)
    elif settings['quiet']:
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.INFO)


def log(*args):
    """Display a message.
    
    Can be disabled with the 'quiet' option (-q)
    """
    logger.info(' '.join([str(msg) for msg in args]))


def debug(*args):
    """Display a debug message.

    Only when activated by the 'debug' option
    """
    logger.debug(' '.join([str(msg) for msg in args]))


def idle(func):
    def callback(*args, **kwargs):
        GLib.idle_add(func, *args, **kwargs)
    return callback
