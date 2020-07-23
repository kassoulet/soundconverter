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

from gettext import gettext as _
from multiprocessing import cpu_count
from gi.repository import Gio


"""Holds all the settings for both cli arguments as well as Gio settings (as configured in the UI)."""


# those settings may be remembered across restarts of soundconverter by default by using dconf.
# Use get_gio_settings instead of importing this directly, because this object changes in tests
_gio_settings = Gio.Settings(schema='org.soundconverter')


# application-wide settings that need to be specified each time soundconverter starts over the command line.
# This also contains all the batch mode settings.
# May be populated with extra values that are derived from _gio_settings
settings = {
    'mode': 'gui',
    'quiet': False,
    'debug': False,
    'cli-output-type': 'audio/x-vorbis',
    'cli-output-suffix': '.ogg',
    'jobs': None,
    'cpu-count': cpu_count(),
    'forced-jobs': None,
}


def set_gio_settings(settings):
    """To overwrite the default Gio.Settings object to for example use a memory backend instead.
    
    Parameters
    ----------
    settings : Gio.Settings
        You can get this by using for example Gio.new_with_backend or Gio.Settings
    """
    global _gio_settings
    _gio_settings = settings


def get_gio_settings():
    """Return the current Gio.Settings object"""
    return _gio_settings
