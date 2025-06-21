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

"""Tests that start soundconverter and try to convert files."""

import os
import shutil
import time
import unittest
from unittest.mock import patch

from util import reset_settings, launch

from soundconverter.gstreamer.converter import available_elements
from soundconverter.gstreamer.discoverer import Discoverer
from soundconverter.interface.batch import cli_convert
from soundconverter.interface.mainloop import gtk_iteration
from soundconverter.util.fileoperations import filename_to_uri
from soundconverter.util.settings import get_gio_settings, settings
from soundconverter.util.soundfile import SoundFile

original_available_elements = available_elements.copy()


cwd = os.getcwd()


class BatchIntegration(unittest.TestCase):
    @classmethod
    def setUp(cls):
        os.makedirs("tests/tmp", exist_ok=True)

    def tearDown(self):
        # tests may change the cwd
        os.chdir(cwd)
        reset_settings()
        if os.path.isdir("tests/tmp/"):
            shutil.rmtree("tests/tmp")
        available_elements.update(original_available_elements)

    def test_single_file_m4a(self):
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp/64",
                "-f",
                "m4a",
                "-q",
                "64",
            ]
        )
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp/320",
                "-f",
                "m4a",
                "-q",
                "320",
            ]
        )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], False)
        self.assertTrue(os.path.isfile("tests/tmp/320/a.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/64/a.m4a"))
        size_320 = os.path.getsize("tests/tmp/320/a.m4a")
        size_64 = os.path.getsize("tests/tmp/64/a.m4a")
        self.assertLess(size_64, size_320)

    def discover(self, path):
        """Run a Discoverer task on the path and return the sound_file.

        Get discovered info with `sound_file.info`, `sound_file.tags` and
        `sound_file.duration`.
        """
        sound_file = SoundFile(filename_to_uri(path))
        discoverer = Discoverer([sound_file])
        discoverer.run()
        while discoverer.discovered != 1:
            gtk_iteration(True)
        return sound_file

    def get_bitrate(self, path):
        """Read the bitrate from a file. Only works with constant bitrates."""
        sound_file = self.discover(path)
        return sound_file.info.get_audio_streams()[0].get_bitrate() / 1000

    def test_vbr(self):
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp/8",
                "-f",
                "mp3",
                "-m",
                "vbr",
                "-q",
                8,  # smaller
            ]
        )
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp/2",
                "-f",
                "mp3",
                "-m",
                "vbr",
                "-q",
                2,
            ]
        )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], False)
        self.assertTrue(os.path.isfile("tests/tmp/8/a.mp3"))
        self.assertTrue(os.path.isfile("tests/tmp/2/a.mp3"))
        size_8 = os.path.getsize("tests/tmp/8/a.mp3")
        size_2 = os.path.getsize("tests/tmp/2/a.mp3")
        # it should be significantly smaller
        self.assertLess(size_8, size_2 / 2)
        # fails to read bitrate of vbr:
        self.assertEqual(self.get_bitrate("tests/tmp/2/a.mp3"), 0)

    def test_abr(self):
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp/320",
                "-f",
                "mp3",
                "-m",
                "abr",
                "-q",
                320,
            ]
        )
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp/112",
                "-f",
                "mp3",
                "-m",
                "abr",
                "-q",
                112,
            ]
        )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], False)
        self.assertTrue(os.path.isfile("tests/tmp/320/a.mp3"))
        self.assertTrue(os.path.isfile("tests/tmp/112/a.mp3"))
        size_320 = os.path.getsize("tests/tmp/320/a.mp3")
        size_112 = os.path.getsize("tests/tmp/112/a.mp3")
        self.assertLess(size_112, size_320 / 2)
        # fails to read bitrate of abr:
        self.assertEqual(self.get_bitrate("tests/tmp/112/a.mp3"), 0)

    def test_cbr(self):
        launch(
            [
                "-b",
                "tests/test data/audio/a.wav",
                "-o",
                "tests/tmp",
                "-f",
                "mp3",
                "-m",
                "cbr",
                "-q",
                256,
            ]
        )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], False)
        self.assertTrue(os.path.isfile("tests/tmp/a.mp3"))
        self.assertEqual(self.get_bitrate("tests/tmp/a.mp3"), 256)

    def test_non_recursive_with_folder(self):
        # it should exit with code 1, because no files are supplied
        with self.assertRaises(SystemExit) as ctx:
            launch(["-b", "tests/test data/empty", "-f", "mp3", "-o", "tmp"])
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], False)
        exit_code = ctx.exception.code
        self.assertEqual(exit_code, 1)

    def test_recursive_empty(self):
        # it should exit with code 2, because files are found but they
        # are not audio files
        with self.assertRaises(SystemExit) as cm:
            launch(
                ["-b", "-r", "tests/test data/empty", "-f", "mp3", "-o", "tmp", "-d"]
            )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], True)
        self.assertEqual(settings["recursive"], True)
        the_exception = cm.exception
        self.assertEqual(the_exception.code, 2)

    def test_recursive_audio(self):
        # it should convert
        launch(
            [
                "-b",
                "tests/test data/audio",
                "-r",
                "-o",
                "tests/tmp",
                "-f",
                "wav",
                "-q",
                24,
            ]
        )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], True)
        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.wav"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.wav"))

        # mono
        bitrate = self.get_bitrate("tests/tmp/audio/b/c.wav")
        self.assertEqual(bitrate, 44100 * 24 / 1000)

        # stereo
        bitrate = self.get_bitrate("tests/tmp/audio/a.wav")
        self.assertEqual(bitrate, 44100 * 24 / 1000 * 2)

    def test_multiple_paths(self):
        # it should convert
        launch(
            [
                "-b",
                "tests/test data/audio",
                "tests/test data/audio/a.wav",
                "tests/test data/empty",
                "-r",
                "-o",
                "tests/tmp",
                "-f",
                "opus",
                "-d",
            ]
        )
        self.assertEqual(settings["main"], "batch")
        self.assertEqual(settings["debug"], True)
        self.assertEqual(settings["recursive"], True)
        # The batch mode behaves like the cp command:
        # - input is a folder, has to provide -r, output is a folder
        # - input is a file, output is a file
        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.opus"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.opus"))
        # a.wav was provided twice, so here is it again but this time without
        # subfolder, just like the input.
        self.assertTrue(os.path.isfile("tests/tmp/a.opus"))

        # since the converison is done, the remaining time should stay
        # constant
        conversion_queue = cli_convert[0].conversions
        remaining_before = conversion_queue.get_remaining()
        time.sleep(0.01)
        remaining_after = conversion_queue.get_remaining()
        self.assertEqual(remaining_before, remaining_after)

    def test_tags(self):
        # it should run and not raise exceptions
        launch(["-t", "tests/test data/", "-r"])
        self.assertEqual(settings["main"], "tags")
        self.assertEqual(settings["debug"], False)
        self.assertEqual(settings["recursive"], True)

    def test_single_subdir_input(self):
        os.chdir("tests")
        # at some point this did not work, keep this spec even if it doesn't
        # appear to add value over test_recursive_audio
        launch(
            ["-b", "test data", "-r", "-f", "flac", "-o", "tmp"],
            "../bin/soundconverter",
        )
        # the input directory is part of the output
        self.assertTrue(os.path.isdir("tmp/test data/audio/"))
        self.assertTrue(os.path.isfile("tmp/test data/audio/a.flac"))
        self.assertTrue(os.path.isfile("tmp/test data/audio/b/c.flac"))

    def test_pattern_1(self):
        launch(
            [
                "-b",
                "tests/test data/audio/",
                "-r",
                "-o",
                "tests/tmp",
                "-p",
                "/{artist}/{album}",
                "-f",
                "m4a",
            ]
        )
        # since pattern is used, the "audio" part of the input path
        # is omitted and not reconstructed. e.g. "audio" might also be an
        # album name, in which case the old structure should be replaced
        # with the provided one.
        self.assertTrue(os.path.isfile("tests/tmp/test_artist/test_album.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/Unknown Artist/Unknown Album.m4a"))

    def test_pattern_2(self):
        launch(
            [
                "-b",
                "tests/test data/audio/b/c.mp3",
                "tests/test data/audio/a.wav",
                "-r",
                "-o",
                "tests/tmp",
                "-p",
                "{Artist}/{bar}/{filename}",
                "-f",
                "m4a",
            ]
        )
        self.assertTrue(os.path.isfile("tests/tmp/test_artist/Unknown Bar/c.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/Unknown Artist/Unknown Bar/a.m4a"))

    def test_skip_overwrite(self):
        path = "tests/tmp/c.m4a"
        now = time.time()

        os.system('touch -d "2 hours ago" {}'.format(path))
        time_1 = os.path.getmtime(path)
        size_1 = os.path.getsize(path)
        # an empty file from 2 hours ago
        self.assertLess(abs(time_1 - (now - 60 * 60 * 2)), 10)
        self.assertEqual(size_1, 0)

        launch(
            [
                "-b",
                "tests/test data/audio/b/c.mp3",
                "-o",
                "tests/tmp",
                "-f",
                "m4a",
                "-e",
                "skip",
            ]
        )
        time_2 = os.path.getmtime(path)
        size_2 = os.path.getsize(path)
        # unchanged
        self.assertEqual(size_2, size_1)
        self.assertEqual(time_2, time_1)
        self.assertTrue(os.path.isfile(path))

        launch(
            [
                "-b",
                "tests/test data/audio/b/c.mp3",
                "-o",
                "tests/tmp",
                "-f",
                "m4a",
                "-e",
                "overwrite",
            ]
        )
        time_3 = os.path.getmtime(path)
        size_3 = os.path.getsize(path)
        # larger and newer file
        self.assertGreater(size_3, size_2)
        self.assertLess(abs(time_3 - now), 10)

    def test_increment_1(self):
        for _ in range(3):
            launch(
                [
                    "-b",
                    "tests/test data/audio/b/c.mp3",
                    "-o",
                    "tests/tmp",
                    "-f",
                    "m4a",
                    "-e",
                    "increment",
                ]
            )
        self.assertTrue(os.path.isfile("tests/tmp/c.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/c (1).m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/c (2).m4a"))

    def test_increment_2(self):
        # increments by default
        for _ in range(3):
            launch(
                ["-b", "tests/test data/audio/b/c.mp3", "-o", "tests/tmp", "-f", "m4a"]
            )
        self.assertTrue(os.path.isfile("tests/tmp/c.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/c (1).m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/c (2).m4a"))

    def test_set_delete_original_false(self):
        gio_settings = get_gio_settings()
        gio_settings.set_boolean("delete-original", True)
        gio_settings = get_gio_settings()
        self.assertTrue(gio_settings.get_boolean("delete-original"))
        launch(["-b", "tests/test data/audio/b/c.mp3", "-o", "tests/tmp", "-f", "m4a"])
        gio_settings = get_gio_settings()
        self.assertFalse(gio_settings.get_boolean("delete-original"))

    def test_set_delete_original_true(self):
        gio_settings = get_gio_settings()
        gio_settings.set_boolean("delete-original", False)
        gio_settings = get_gio_settings()
        self.assertFalse(gio_settings.get_boolean("delete-original"))

        os.system('cp "tests/test data/audio/a.wav" "tests/tmp/a.wav"')
        self.assertTrue(os.path.isfile("tests/tmp/a.wav"))

        launch(
            [
                "-b",
                "tests/tmp/a.wav",
                "-o",
                "tests/tmp",
                "-f",
                "m4a",
                "-D",
            ]
        )

        gio_settings = get_gio_settings()
        self.assertTrue(gio_settings.get_boolean("delete-original"))
        self.assertFalse(os.path.isfile("tests/tmp/a.wav"))

    def test_set_output_resample(self):
        gio_settings = get_gio_settings()
        self.assertFalse(gio_settings.get_boolean("output-resample"))
        self.assertEqual(48000, gio_settings.get_int("resample-rate"))

        os.system('cp "tests/test data/audio//b/c.mp3" "tests/tmp/c.mp3"')
        self.assertTrue(os.path.isfile("tests/tmp/c.mp3"))

        sample_rate = 8000

        launch(
            [
                "-b",
                "tests/tmp/c.mp3",
                "-o",
                "tests/tmp",
                "-f",
                "wav",
                "-R",
                str(sample_rate),
            ]
        )

        gio_settings = get_gio_settings()
        self.assertTrue(gio_settings.get_boolean("output-resample"))
        self.assertEqual(gio_settings.get_int("resample-rate"), sample_rate)
        self.assertEqual(
            self.get_bitrate("tests/tmp/c.wav"), sample_rate * 8 / 1000 * 2
        )

    def test_conversion_no_tags(self):
        launch(
            [
                "-b",
                "tests/test data/no tags",
                "-r",
                "-o",
                "tests/tmp",
                "-f",
                "m4a",
                "-d",
            ]
        )

        self.assertTrue(os.path.isdir("tests/tmp/"))
        self.assertTrue(os.path.isfile("tests/tmp/no tags/no-tags.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/no tags/no-tags (1).m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/no tags/no-tags (2).m4a"))

    def test_wont_fail_with_recursion_error(self):
        # converting and skipping files won't cause a super long recursion chain,
        # like it used to https://bugs.launchpad.net/soundconverter/+bug/1952551
        # GLib.idle_add seems to start a new call chain, fixing this issue.
        path = "soundconverter.gstreamer.discoverer.DiscovererThread._analyse_file"

        def _analyse_file(_, sound_file):
            # to speed the test up
            sound_file.readable = True

        with patch(path, _analyse_file):
            launch(
                [
                    "-b",
                    "tests/bulk-test-data",
                    "-r",
                    "-o",
                    "tests/tmp",
                    "-f",
                    "mp3",
                    "-q",
                    8,
                ]
            )

            self.assertTrue(os.path.isdir("tests/tmp/bulk-test-data"))
            self.assertEqual(len(os.listdir("tests/tmp/bulk-test-data")), 300)

            # won't raise an exception
            launch(
                [
                    "-b",
                    "tests/bulk-test-data",
                    "-r",
                    "-o",
                    "tests/tmp",
                    "-f",
                    "mp3",
                    "-q",
                    8,
                    "-e",
                    "skip",
                    "-j",
                    1,
                ]
            )

            self.assertEqual(len(os.listdir("tests/tmp/bulk-test-data")), 300)


if __name__ == "__main__":
    unittest.main()
