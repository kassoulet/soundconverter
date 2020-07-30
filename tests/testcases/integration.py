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

"""Tests that start soundconverter and try to convert files."""


import unittest
from unittest.mock import patch
import os
import sys
import shutil
import urllib.parse
from gi.repository import Gio, Gtk
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

from soundconverter.util.settings import get_gio_settings
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.fileoperations import filename_to_uri
from soundconverter.interface.ui import win, gtk_iteration

from util import reset_settings


def launch(argv=[]):
    """Start the soundconverter with the command line argument array argv."""
    testargs = sys.argv.copy()[:2]
    testargs += argv
    with patch.object(sys, 'argv', testargs):
        spec = spec_from_loader("launcher", SourceFileLoader("launcher", "bin/soundconverter"))
        spec.loader.exec_module(module_from_spec(spec))


def quote(ss):
    if isinstance(ss, str):
        ss = ss.encode('utf-8')
    return urllib.parse.quote(ss)


class Batch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs("tests/tmp", exist_ok=True)

    def tearDown(self):
        reset_settings()
        if os.path.isdir("tests/tmp/"):
            shutil.rmtree("tests/tmp")

    def testNonRecursiveWithFolder(self):
        # it should exit with code 1, because no files are supplied
        with self.assertRaises(SystemExit) as ctx:
            launch([
                "-b", "-q", "tests/test data/empty", "-m", "audio/mpeg"
            ])
        exit_code = ctx.exception.code
        self.assertEqual(exit_code, 1)

    def testRecursiveEmpty(self):
        # it should exit with code 2, because files are found but they
        # are not audiofiles
        with self.assertRaises(SystemExit) as cm:
            launch([
                "-b", "-r", "-q", "tests/test data/empty", "-m", "audio/mpeg"
            ])
        the_exception = cm.exception
        self.assertEqual(the_exception.code, 2)

    def testRecursiveAudio(self):
        # it should convert
        launch([
            "-b", "tests/test data/audio",
            "-r",
            "-q",
            "-o", "tests/tmp",
            "-m", "audio/mpeg"
            ])
        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.mp3"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.mp3"))

    def testMultiplePaths(self):
        # it should convert
        launch([
            "-b",
            "tests/test data/audio",
            "tests/test data/audio/a.wav",
            "tests/test data/empty",
            "-r",
            "-q",
            "-o", "tests/tmp",
            "-m", "audio/x-m4a"
            ])
        # The batch mode behaves like the cp command:
        # - input is a folder, has to provide -r, output is a folder
        # - input is a file, output is a file
        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.m4a"))
        self.assertTrue(os.path.isfile("tests/tmp/a.m4a"))


class GUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isdir("tests/tmp/"):
            shutil.rmtree("tests/tmp")
        os.makedirs("tests/tmp", exist_ok=True)

    def tearDown(self):
        win[0].close()
        reset_settings()
        if os.path.isdir("tests/tmp/"):
            shutil.rmtree("tests/tmp")

    def testConversion(self):
        launch([
            "tests/test data/audio/a.wav",
            "tests/test data/audio/strângë chàrs фズ.wav",
            "tests/test data/audio/",
            "tests/test data/empty"
        ])
        window = win[0]

        # check if directory is read correctly
        expected_filelist = [
            "tests/test data/audio/a.wav",
            "tests/test data/audio/strângë chàrs фズ.wav",
            "tests/test data/audio/b/c.mp3"
        ]
        self.assertCountEqual(
            [filename_to_uri(path) for path in expected_filelist],
            win[0].filelist.filelist
        )

        # setup for conversion
        window.prefs.change_mime_type('audio/ogg; codecs=opus')
        settings = get_gio_settings()
        settings.set_boolean('create-subfolders', False)
        settings.set_boolean('same-folder-as-input', False)
        settings.set_string('selected-folder', os.path.abspath("tests/tmp"))
        settings.set_int('name-pattern-index', 0)
        settings.set_boolean('replace-messy-chars', True)
        settings.set_boolean('delete-original', False)

        # start conversion
        window.on_convert_button_clicked()

        # wait for the assertions until all files are converted
        while window.converter.finished_tasks < len(expected_filelist):
            # as Gtk.main is replaced by gtk_iteration, the unittests
            # are responsible about when soundconverter continues
            # to work on the conversions and updating the GUI
            gtk_iteration()

        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.opus"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/strange_chars_.opus"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.opus"))
        # no duplicates in the GUI:
        self.assertFalse(os.path.isfile("tests/tmp/a.opus"))


if __name__ == "__main__":
    unittest.main()
