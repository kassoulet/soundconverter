#!/usr/bin/python3
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2025 Gautier Portet
# Copyright 2020-2025 Sezanzeb
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


"""Holds all the settings for both cli arguments as well as Gio settings.

Gio Settings are set in the UI and retained over restarts. In batch mode,
some of the CLI args are written into that temporarily.
"""

from multiprocessing import cpu_count
from typing import Any, Dict

from gi.repository import Gio

# Use get_gio_settings instead of importing this directly, because this
# object changes in tests, and also this object will be replaced with a
# memory backend for the batch mode.
_gio_settings: Gio.Settings = Gio.Settings(schema="org.soundconverter")  # do not import!


def get_gio_settings() -> Gio.Settings:
    """Return the current Gio.Settings object.

    Use this isntead of importing _gio_settings directly.
    """
    return _gio_settings


# Arguments that can exclusively set over the CLI
settings: Dict[str, Any] = {"main": "gui", "debug": False}


def set_gio_settings(settings: Gio.Settings) -> None:
    """Overwrite the default Gio.Settings object.

    For example use a memory backend instead.

    Parameters
    ----------
    settings : Gio.Settings
        You can get this by using for example Gio.new_with_backend or
        Gio.Settings
    """
    global _gio_settings
    _gio_settings = settings


def get_num_jobs() -> int:
    """Return the number of jobs that should be run in parallel."""
    return (
        _gio_settings.get_int("number-of-jobs")
        if _gio_settings.get_boolean("limit-jobs")
        else cpu_count()
    )
