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


def _notification_dummy(message):
    pass


notification = _notification_dummy

try:
    import gi
    gi.require_version('Notify', '0.7')
    from gi.repository import Notify

    def _notification(message):
        try:
            Notify.Notification('SoundConverter', message).show()
        except Exception:
            pass

    if Notify.init('Basics'):
        notification = _notification

except (ImportError, ValueError):
    pass
