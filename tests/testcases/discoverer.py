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

import os
import unittest

from gi.repository import GLib

from soundconverter.gstreamer.discoverer import Discoverer
from soundconverter.util.soundfile import SoundFile


class DiscovererTest(unittest.TestCase):
    """Checks if async Task class functions are working properly."""
    def test_read_tags(self):
        c_mp3 = 'file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3')
        discoverer = Discoverer(SoundFile(c_mp3))
        discoverer.set_callback(lambda _: None)
        discoverer.run()
        # should be asynchronous, nothing done yet
        self.assertEqual(discoverer.readable, None)
        self.assertEqual(len(discoverer.sound_file.tags), 0)

        while discoverer.readable is None:
            loop = GLib.MainLoop()
            context = loop.get_context()
            context.iteration(True)

        self.assertTrue(discoverer.readable)
        self.assertEqual(discoverer.sound_file.tags['artist'], 'test_artist')
        self.assertEqual(discoverer.sound_file.tags['album'], 'test_album')

    def test_not_audio(self):
        c_mp3 = 'file://' + os.path.realpath('tests/test%20data/empty/a')
        discoverer = Discoverer(SoundFile(c_mp3))
        discoverer.set_callback(lambda _: None)
        discoverer.run()
        # should be asynchronous, nothing done yet
        self.assertEqual(discoverer.readable, None)
        self.assertEqual(len(discoverer.sound_file.tags), 0)

        while discoverer.readable is None:
            loop = GLib.MainLoop()
            context = loop.get_context()
            context.iteration(True)

        self.assertFalse(discoverer.readable)
        self.assertEqual(len(discoverer.sound_file.tags), 0)

if __name__ == "__main__":
    unittest.main()
