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

import unittest
from soundconverter.util.formats import (
    get_mime_type,
    get_quality,
    get_bitrate_from_settings,
    get_file_extension,
    get_default_quality,
)
from soundconverter.util.settings import get_gio_settings


class Format(unittest.TestCase):
    def test_get_quality(self):
        self.assertEqual(get_quality("audio/mpeg", 0, "cbr"), 64)
        self.assertEqual(get_quality("audio/x-m4a", 1, "thetgdfgsfd"), 96)
        self.assertEqual(get_quality("audio/x-m4a", 256, reverse=True), 4)
        self.assertEqual(get_quality("audio/mpeg", 320, mode="abr", reverse=True), 5)
        self.assertEqual(get_quality("audio/mpeg", -1, mode="abr", reverse=False), 320)
        self.assertEqual(get_quality("audio/mpeg", -2, mode="cbr", reverse=False), 256)

    def test_get_default_quality(self):
        self.assertEqual(get_default_quality("audio/mpeg"), 0)
        self.assertEqual(get_default_quality("audio/mpeg", "vbr"), 0)
        self.assertEqual(get_default_quality("audio/mpeg", "cbr"), 320)
        self.assertEqual(get_default_quality("audio/mpeg", "abr"), 320)
        self.assertEqual(get_default_quality("audio/x-m4a"), 400)

    def test_get_bitrate_from_settings(self):
        # Use bitrates that are not part of the indexing triggered by the ui,
        # to ensure the code is flexible for custom bitrates (such as set in
        # the batch mode)
        get_gio_settings().set_string("output-mime-type", "audio/mpeg")
        get_gio_settings().set_int("mp3-abr-quality", 200)
        get_gio_settings().set_string("mp3-mode", "abr")
        self.assertEqual(get_bitrate_from_settings(), "~200 kbps")
        get_gio_settings().set_int("mp3-vbr-quality", 200)
        get_gio_settings().set_string("mp3-mode", "vbr")
        self.assertEqual(get_bitrate_from_settings(), "N/A")
        get_gio_settings().set_int("mp3-cbr-quality", 200)
        get_gio_settings().set_string("mp3-mode", "cbr")
        self.assertEqual(get_bitrate_from_settings(), "200 kbps")

        get_gio_settings().set_string("output-mime-type", "audio/ogg; codecs=opus")
        get_gio_settings().set_int("opus-bitrate", 123)
        self.assertEqual(get_bitrate_from_settings(), "~123 kbps")

        get_gio_settings().set_string("output-mime-type", "audio/x-m4a")
        get_gio_settings().set_int("aac-quality", 234)
        self.assertEqual(get_bitrate_from_settings(), "~234 kbps")

        get_gio_settings().set_string("output-mime-type", "audio/x-vorbis")
        get_gio_settings().set_double("vorbis-quality", 0.99)
        self.assertEqual(get_bitrate_from_settings(), "~500 kbps")

        get_gio_settings().set_string("output-mime-type", "audio/x-vorbis")
        get_gio_settings().set_double("vorbis-quality", 0.21)
        self.assertEqual(get_bitrate_from_settings(), "~96 kbps")

        get_gio_settings().set_string("output-mime-type", "audio/x-flac")
        self.assertEqual(get_bitrate_from_settings(), "N/A")

        get_gio_settings().set_string("output-mime-type", "audio/x-wav")
        get_gio_settings().set_boolean("output-resample", False)
        rate = 705.6
        self.assertEqual(get_bitrate_from_settings(), "{} kbps".format(rate))
        get_gio_settings().set_boolean("output-resample", True)
        get_gio_settings().set_int("resample-rate", 44100)
        get_gio_settings().set_int("wav-sample-width", 16)
        self.assertEqual(get_bitrate_from_settings(), "{} kbps".format(rate))
        get_gio_settings().set_int("wav-sample-width", 32)
        self.assertEqual(get_bitrate_from_settings(), "{} kbps".format(rate * 2))
        get_gio_settings().set_int("wav-sample-width", 8)
        get_gio_settings().set_int("resample-rate", 128000)
        self.assertEqual(
            get_bitrate_from_settings(), "{} kbps".format(rate / 44.1 * 128 / 2)
        )

    def test_get_file_extension(self):
        self.assertEqual(get_file_extension("audio/x-flac"), "flac")
        self.assertEqual(get_file_extension("flac"), "flac")

    def test_get_mime_type(self):
        self.assertEqual(get_mime_type("flac"), "audio/x-flac")
        self.assertEqual(get_mime_type("audio/x-flac"), "audio/x-flac")
        self.assertEqual(get_mime_type("mp3"), "audio/mpeg")
        self.assertEqual(get_mime_type("audio/mpeg"), "audio/mpeg")


if __name__ == "__main__":
    unittest.main()
