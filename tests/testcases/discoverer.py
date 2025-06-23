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

import os
import time
import unittest
from unittest.mock import Mock

from gi.repository import GLib

from soundconverter.gstreamer.discoverer import (
    Discoverer,
    add_discoverers,
    is_denylisted,
)
from soundconverter.interface.mainloop import gtk_iteration
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.taskqueue import TaskQueue


class DiscovererQueueTest(unittest.TestCase):
    def setUp(self):
        self.gio_settings = get_gio_settings()
        queue = TaskQueue()
        parent_dir = "file://" + os.getcwd()
        self.sound_files = [
            SoundFile(parent_dir + "/tests/test%20data/audio/b/c.mp3"),
            SoundFile(parent_dir + "/tests/test%20data/audio/a.wav"),
            SoundFile(parent_dir + "/tests/test%20data/empty/b/c"),
            # add_discoverers will split it here into two tasks or something. Make sure
            # each of them gets at least one valid audio file in order to test that they
            # are doing their stuff in parallel.
            SoundFile(parent_dir + "/tests/test%20data/audio/strângë chàrs фズ.wav"),
            SoundFile(parent_dir + "/tests/test%20data/empty/a"),
        ]
        self.queue = queue

    def wait_for_queue(self):
        while len(self.queue.done) < len(self.queue.all_tasks):
            # wait for the test to copmlete
            time.sleep(0.01)
            gtk_iteration()

    def tearDown(self):
        self.wait_for_queue()

    def test_add_discoverers(self):
        sound_files = self.sound_files
        queue = self.queue
        self.gio_settings.set_boolean("limit-jobs", True)
        self.gio_settings.set_int("number-of-jobs", 2)
        add_discoverers(queue, sound_files)

        self.assertEqual(len(queue.all_tasks), 2)
        self.assertEqual(len(queue.running), 0)

        for sound_file in sound_files:
            self.assertFalse(sound_file.readable)

        queue.run()
        # two tasks are running at the same time
        self.assertEqual(len(queue.running), 2)

        # add_discoverers creates only one task per job, each task handles
        # multiple sound_files, as opposed to the converter, which only
        # works on a single sound_file.
        self.assertEqual(len(queue.all_tasks), 2)

        self.wait_for_queue()

        # correctly figures out which sound_files contain readable information
        self.assertTrue(sound_files[0].readable)
        self.assertTrue(sound_files[1].readable)
        self.assertFalse(sound_files[2].readable)
        self.assertTrue(sound_files[3].readable)
        self.assertFalse(sound_files[4].readable)


class DiscovererTest(unittest.TestCase):
    """Checks if async Task class functions are working properly."""

    def test_read_tags(self):
        c_mp3 = "file://" + os.path.realpath("tests/test%20data/audio/b/c.mp3")
        discoverer = Discoverer([SoundFile(c_mp3)])
        discoverer.connect("done", lambda _: None)
        discoverer.run()

        done = Mock()
        discoverer.connect("done", done)
        discoverer.run()

        # needs to iterate the main loop for messages on the bus
        loop = GLib.MainLoop()
        while discoverer.running:
            context = loop.get_context()
            context.iteration(True)

        done.assert_called_with(discoverer)

        sound_file = discoverer.sound_files[0]
        self.assertTrue(sound_file.readable)
        print(sound_file.duration)
        self.assertEqual(int(sound_file.duration), 1)
        self.assertEqual(sound_file.tags["artist"], "test_artist")
        self.assertEqual(sound_file.tags["album"], "test_album")

    def test_read_tags_multiple(self):
        c_mp3 = "file://" + os.path.realpath("tests/test%20data/audio/b/c.mp3")
        a_wav = "file://" + os.path.realpath("tests/test%20data/audio/a.wav")
        empty_a = "file://" + os.path.realpath("tests/test%20data/empty/a")
        sound_files = [SoundFile(c_mp3), SoundFile(empty_a), SoundFile(a_wav)]

        discoverer = Discoverer(sound_files)
        discoverer.connect("done", lambda _: None)

        done = Mock()
        discoverer.connect("done", done)
        discoverer.run()

        # needs to iterate the main loop for messages on the bus
        loop = GLib.MainLoop()
        while discoverer.running:
            context = loop.get_context()
            context.iteration(True)

        done.assert_called_with(discoverer)

        self.assertTrue(sound_files[0].readable)
        self.assertEqual(sound_files[0].tags["artist"], "test_artist")
        self.assertEqual(sound_files[0].tags["album"], "test_album")
        self.assertEqual(int(sound_files[0].duration), 1)

        self.assertFalse(sound_files[1].readable)
        self.assertEqual(len(sound_files[1].tags), 0)
        self.assertIsNone(sound_files[1].duration)

        self.assertTrue(sound_files[2].readable)
        # 'container-format' happens to be read from wav files, but there is
        # no special need in having it. can be used for tests though
        self.assertEqual(sound_files[2].tags["container-format"], "WAV")
        self.assertLess(abs(sound_files[2].duration - 1.00), 0.01)

    def test_not_audio(self):
        empty = "file://" + os.path.realpath("tests/test%20data/empty/a")
        a_iso = "file://" + os.path.realpath("tests/test%20data/a.iso")
        image_jpg = "file://" + os.path.realpath("tests/test%20data/image.jpg")
        discoverer = Discoverer(
            [SoundFile(empty), SoundFile(a_iso), SoundFile(image_jpg)]
        )
        discoverer.connect("done", lambda _: None)
        discoverer.run()

        done = Mock()
        discoverer.connect("done", done)
        discoverer.run()

        loop = GLib.MainLoop()
        while discoverer.running:
            context = loop.get_context()
            context.iteration(True)

        done.assert_called_with(discoverer)

        self.assertEqual(len(discoverer.sound_files), 3)
        for sound_file in discoverer.sound_files:
            self.assertFalse(sound_file.readable)
            self.assertIsNone(sound_file.duration)
            self.assertEqual(len(sound_file.tags), 0)

        self.assertEqual(is_denylisted(discoverer.sound_files[1]), "*.iso")


if __name__ == "__main__":
    unittest.main()
