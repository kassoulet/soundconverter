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

from typing import Any, Callable, Dict

from gi.repository import Gtk


class GladeWindow:
    callbacks: Dict[str, Callable] = {}
    builder: Gtk.Builder = None

    def __init__(self, builder: Gtk.Builder) -> None:
        """Init GladeWindow, store the objects's potential callbacks for later.

        You have to call connect_signals() when all descendants are ready.
        """
        GladeWindow.builder = builder
        callbacks_dict: Dict[str, Callable] = {}
        for x in dir(self):
            if x.startswith("on_"):
                callbacks_dict[x] = getattr(self, x)
        GladeWindow.callbacks.update(callbacks_dict)

    def __getattr__(self, attribute: str) -> Any:
        """Allow direct use of window widget."""
        widget = GladeWindow.builder.get_object(attribute)
        if widget is None:
            raise AttributeError(f"Widget '{attribute}' not found")
        self.__dict__[attribute] = widget  # cache result
        return widget

    @staticmethod
    def connect_signals() -> None:
        """Connect all GladeWindow objects to theirs respective signals."""
        GladeWindow.builder.connect_signals(GladeWindow.callbacks)
