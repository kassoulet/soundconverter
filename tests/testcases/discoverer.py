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
import time
from unittest.mock import Mock

from gi.repository import GLib

from soundconverter.gstreamer.discoverer import Discoverer, is_denylisted, \
    add_discoverers
from soundconverter.util.taskqueue import TaskQueue
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.settings import get_gio_settings
from soundconverter.interface.ui import gtk_iteration


class DiscovererQueueTest(unittest.TestCase):
    def setUp(self):
        self.gio_settings = get_gio_settings()
        queue = TaskQueue()
        parent = 'file://' + os.getcwd()
        sound_files = [
            SoundFile(parent + '/tests/test%20data/audio/b/c.mp3'),
            SoundFile(parent + '/tests/test%20data/audio/a.wav'),
            SoundFile(parent + '/tests/test%20data/audio/strângë chàrs фズ.wav'),
            SoundFile(parent + '/tests/test%20data/empty/a'),
            SoundFile(parent + '/tests/test%20data/empty/b/c')
        ]
        self.queue = queue
        self.sound_files = sound_files

    def test_add_discoverers(self):
        sound_files = self.sound_files
        queue = self.queue
        self.gio_settings.set_boolean('limit-jobs', True)
        self.gio_settings.set_int('number-of-jobs', 2)
        add_discoverers(queue, sound_files)

        self.assertEqual(len(queue.all_tasks), 2)
        self.assertEqual(len(queue.running), 0)

        for sound_file in sound_files:
            self.assertFalse(sound_file.readable)

        queue.run()
        self.assertEqual(len(queue.running), 2)
        # add_discoverers creates only one task per job, each task handles
        # multiple sound_files, as opposed to the converter, which only
        # works on a single sound_file.
        self.assertEqual(len(queue.all_tasks), 2)

        while len(queue.done) < 2:
            time.sleep(0.01)
            gtk_iteration()

        self.assertTrue(sound_files[0].readable)
        self.assertTrue(sound_files[1].readable)
        self.assertTrue(sound_files[2].readable)
        self.assertFalse(sound_files[3].readable)
        self.assertFalse(sound_files[4].readable)


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
        self.assertLess(abs(sound_file.duration - 1.04), 0.01)
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
        self.assertLess(abs(sound_files[0].duration - 1.04), 0.01)

        self.assertFalse(sound_files[1].readable)
        self.assertEqual(len(sound_files[1].tags), 0)
        self.assertIsNone(sound_files[1].duration)

        self.assertTrue(sound_files[2].readable)
        # 'container-format' happens to be read from wav files, but there is
        # no special need in having it. can be used for tests though
        self.assertEqual(sound_files[2].tags['container-format'], 'WAV')
        self.assertLess(abs(sound_files[2].duration - 1.00), 0.01)

    def test_not_audio(self):
        c_mp3 = 'file://' + os.path.realpath('tests/test%20data/empty/a')
        a_iso = 'file://' + os.path.realpath('tests/test%20data/a.iso')
        discoverer = Discoverer([SoundFile(c_mp3), SoundFile(a_iso)])
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
        self.assertIsNone(sound_file.duration)
        self.assertFalse(sound_file.readable)
        self.assertEqual(len(sound_file.tags), 0)

        sound_file = discoverer.sound_files[1]
        self.assertEqual(is_denylisted(sound_file), '*.iso')
        self.assertIsNone(sound_file.duration)
        self.assertFalse(sound_file.readable)
        self.assertEqual(len(sound_file.tags), 0)


if __name__ == "__main__":
    unittest.main()
