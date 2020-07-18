#!/usr/bin/python3
# -*- coding: utf-8 -*-


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

from soundconverter.util.settings import settings, get_gio_settings
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.fileoperations import filename_to_uri
from soundconverter.ui import win, gtk_iteration

from util import reset_settings


def launch(argv=[]):
    """Start the soundconverter with the command line argument array argv.
    
    Make sure to run the `make` command first in your terminal.
    """
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
        with self.assertRaises(SystemExit) as cm:
            launch(["-b", "-q", "tests/test data/empty"])
        the_exception = cm.exception
        self.assertEqual(the_exception.code, 1)

    def testRecursiveEmpty(self):
        # it should exit with code 2, because files are found but they
        # are not audiofiles
        with self.assertRaises(SystemExit) as cm:
            launch(["-b", "-r", "-q", "tests/test data/empty"])
        the_exception = cm.exception
        self.assertEqual(the_exception.code, 2)

    def testRecursiveAudio(self):
        # it should convert
        launch([
            "-b", "tests/test data/audio",
            "-r",
            "-q",
            "-o", "tests/tmp",
            "-m", "mp3",
            "-s", ".mp3"
            ])
        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.mp3"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.mp3"))

    def testMultiplePaths(self):
        # it should convert
        launch([
            "-b", "tests/test data/audio", "tests/test data/audio/a.wav", "tests/test data/empty",
            "-r",
            "-q",
            "-o", "tests/tmp",
            "-m", "audio/x-m4a",
            "-s", ".m4a"
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
        launch(["tests/test data/audio/a.wav", "tests/test data/audio/strângë chàrs фズ.wav",
                "tests/test data/audio/", "tests/test data/empty"])
        window = win[0]

        # check if directory is read correctly
        expectation = ["tests/test data/audio/a.wav", "tests/test data/audio/strângë chàrs фズ.wav",
                       "tests/test data/audio/b/c.mp3"]
        self.assertCountEqual([filename_to_uri(path) for path in expectation], win[0].filelist.filelist)

        # setup for conversion
        window.prefs.change_mime_type('audio/ogg; codecs=opus')
        get_gio_settings().set_boolean('create-subfolders', False)
        get_gio_settings().set_boolean('same-folder-as-input', False)
        get_gio_settings().set_string('selected-folder', os.path.abspath("tests/tmp"))
        get_gio_settings().set_int('name-pattern-index', 0)
        get_gio_settings().set_boolean('replace-messy-chars', True)
        get_gio_settings().set_boolean('delete-original', False)

        # start conversion
        window.on_convert_button_clicked()

        # wait for the assertions until all files are converted
        while window.converter.finished_tasks < len(expectation):
            # as Gtk.main is replaced by gtk_iteration, the unittests
            # are responsible about when soundconverter continues
            # to work on the conversions and updating the GUI
            gtk_iteration()

        print(os.getcwd())
        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.opus"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/strange_chars_.opus"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.opus"))
        # no duplicates in the GUI:
        self.assertFalse(os.path.isfile("tests/tmp/a.opus"))


if __name__ == "__main__":
    unittest.main()
