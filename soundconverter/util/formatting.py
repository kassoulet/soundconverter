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

"""Functions for formatting strings."""


def format_time(seconds):
    units = [(86400, "d"), (3600, "h"), (60, "m"), (1, "s")]
    seconds = round(seconds)
    result = []
    for factor, unity in units:
        count = int(seconds / factor)
        seconds -= count * factor
        if count > 0 or (factor == 1 and not result):
            result.append("{} {}".format(count, unity))
    assert seconds == 0
    return " ".join(result)
