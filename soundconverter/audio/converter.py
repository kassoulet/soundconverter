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

from soundconverter.audio.task import Task


class Converter(Task):
    def __init__(self, source_filename, target_filename, mime, quality):
        """Create a converter that converts a single file."""
        pass
        
    def progress(self):
        """Fraction of how much of the task is completed."""
        raise NotImplementedError()

    def cancel(self):
        """Stop execution of the task."""
        raise NotImplementedError()

    def pause(self):
        """Stop execution of the task."""
        raise NotImplementedError()

    def resume(self):
        """Stop execution of the task."""
        raise NotImplementedError()

    def run(self, callback):
        """Run the task.
        
        Parameters
        ----------
            callback : function
                Call this when done
        """
        raise NotImplementedError()
