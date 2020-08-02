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
from unittest.mock import Mock

from gi.repository import GLib

from soundconverter.gstreamer.discoverer import Discoverer
from soundconverter.util.soundfile import SoundFile


class DiscovererTest(unittest.TestCase):
    """Checks if async Task class functions are working properly."""
    def test_read_tags(self):
        c_mp3 = 'file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3')
        discoverer = Discoverer([SoundFile(c_mp3)])
        discoverer.set_callback(lambda _: None)
        discoverer.run()

        done = Mock()
        discoverer.set_callback(done)
        discoverer.run()

        # needs to iterate the main loop for messages on the bus
        loop = GLib.MainLoop()
        while discoverer.running:
            context = loop.get_context()
            context.iteration(True)

        done.assert_called_with(discoverer)

        sound_file = discoverer.sound_files[0]
        self.assertTrue(sound_file.readable)
        self.assertEqual(sound_file.tags['artist'], 'test_artist')
        self.assertEqual(sound_file.tags['album'], 'test_album')

    def test_read_tags_multiple(self):
        c_mp3 = 'file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3')
        a_wav = 'file://' + os.path.realpath('tests/test%20data/audio/a.wav')
        empty_a = 'file://' + os.path.realpath('tests/test%20data/empty/a')
        sound_files = [
            SoundFile(c_mp3),
            SoundFile(empty_a),
            SoundFile(a_wav)
        ]

        discoverer = Discoverer(sound_files)
        discoverer.set_callback(lambda _: None)

        done = Mock()
        discoverer.set_callback(done)
        discoverer.run()

        # needs to iterate the main loop for messages on the bus
        loop = GLib.MainLoop()
        while discoverer.running:
            context = loop.get_context()
            context.iteration(True)

        done.assert_called_with(discoverer)

        self.assertTrue(sound_files[0].readable)
        self.assertEqual(sound_files[0].tags['artist'], 'test_artist')
        self.assertEqual(sound_files[0].tags['album'], 'test_album')

        self.assertFalse(sound_files[1].readable)
        self.assertEqual(len(sound_files[1].tags), 0)

        self.assertTrue(sound_files[2].readable)
        # 'container-format' happens to be read from wav files, but there is
        # no special need in having it. can be used for tests though
        self.assertEqual(sound_files[2].tags['container-format'], 'WAV')

    def test_not_audio(self):
        c_mp3 = 'file://' + os.path.realpath('tests/test%20data/empty/a')
        discoverer = Discoverer([SoundFile(c_mp3)])
        discoverer.set_callback(lambda _: None)
        discoverer.run()

        done = Mock()
        discoverer.set_callback(done)
        discoverer.run()

        loop = GLib.MainLoop()
        while discoverer.running:
            context = loop.get_context()
            context.iteration(True)

        done.assert_called_with(discoverer)

        sound_file = discoverer.sound_files[0]
        self.assertFalse(sound_file.readable)
        self.assertEqual(len(sound_file.tags), 0)


if __name__ == "__main__":
    unittest.main()
