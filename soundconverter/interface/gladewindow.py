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


class GladeWindow:
    callbacks = {}
    builder = None

    def __init__(self, builder):
        """Init GladeWindow, store the objects's potential callbacks for later.

        You have to call connect_signals() when all descendants are ready.
        """
        GladeWindow.builder = builder
        GladeWindow.callbacks.update(
            dict([[x, getattr(self, x)] for x in dir(self) if x.startswith("on_")]),
        )

    def __getattr__(self, attribute):
        """Allow direct use of window widget."""
        widget = GladeWindow.builder.get_object(attribute)
        if widget is None:
            raise AttributeError(f"Widget '{attribute}' not found")
        self.__dict__[attribute] = widget  # cache result
        return widget

    @staticmethod
    def connect_signals():
        """Connect all GladeWindow objects to theirs respective signals."""
        GladeWindow.builder.connect_signals(GladeWindow.callbacks)
