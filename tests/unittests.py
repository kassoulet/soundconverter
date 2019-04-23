#!/usr/bin/python3
# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch
import os
import sys
import shutil
from urllib.parse import unquote
import urllib.request, urllib.parse, urllib.error
import time

import gi
gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gst, Gio, Gtk, GLib
Gst.init([a for a in sys.argv[1:] if '-gst' in a])

from soundconverter.settings import settings
from soundconverter.namegenerator import TargetNameGenerator
from soundconverter.soundfile import SoundFile
from soundconverter.fileoperations import filename_to_uri
from soundconverter.batch import prepare_files_list
from soundconverter.ui import win, gtk_iteration

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader 

DEFAULT_SETTINGS = settings.copy()


# tests will control gtk main iterations
Gtk.main = gtk_iteration
Gtk.main_quit = lambda: None

def launch(argv=[]):
    """ starts the soundconverter given the command
    line argument array argv. Make sure to run the
    make command first in your terminal. """
    testargs = sys.argv.copy()[:2]
    testargs += argv
    with patch.object(sys, 'argv', testargs):
        spec = spec_from_loader("launcher", SourceFileLoader("launcher", "bin/soundconverter"))
        spec.loader.exec_module(module_from_spec(spec))

def reset_settings():
    """ resets the global settings to their initial state """
    global settings
    # convert to list otherwise del won't work
    for key in list(settings.keys()):
        if key in DEFAULT_SETTINGS:
            settings[key] = DEFAULT_SETTINGS[key]
        else:
            del settings[key]
    # batch tests assume that recursive is off by default:
    assert ((not "recursive" in settings) or (not settings["recursive"]))

def quote(ss):
    if isinstance(ss, str):
        ss = ss.encode('utf-8')
    return urllib.parse.quote(ss)


class FilenameToUriTest(unittest.TestCase):
    def test(self):
        for path in ('foo', '/foo', 'foo/bar', '/foo/bar'):
            uri = filename_to_uri(path)
            self.assertTrue(uri.startswith('file://'))
            self.assertTrue(Gio.file_parse_name(path).get_uri() in uri)

        for path in ('http://example.com/foo', ):
            uri = filename_to_uri(path)
            self.assertTrue(uri.startswith('http://'))
            self.assertTrue(Gio.file_parse_name(path).get_uri() in uri)


class PrepareFilesList(unittest.TestCase):
    def tearDown(self):
        reset_settings()
            
    def testNonRecursiveDirectory(self):
        test = ["tests/testdata/empty/"]
        # it should not find anything, as test is a directory
        expectation = ([], [])
        self.assertEqual(prepare_files_list(test), expectation)

    def testRecursiveDirectory(self):
        settings["recursive"] = True
        test = ["tests/testdata/empty/", "tests/testdata/empty/b"]
        expectation = ([
            filename_to_uri(test[0] + "a"),
            filename_to_uri(test[0] + "b/c"),
            filename_to_uri(test[1] + "/c")
        ], [
            "empty/",
            "empty/b/",
            "b/"
        ])
        result = prepare_files_list(test)
        for path in result[0]:
            self.assertTrue(path.startswith('file://'))
        self.assertEqual(result, expectation)

    def testFile(self):
        test = ["tests/testdata/empty/a"]
        # it should not detect the name of the parent directory as
        # it's only a single file
        expectation = ([filename_to_uri(test[0])], [""])
        result = prepare_files_list(test)
        self.assertTrue(result[0][0].startswith('file://'))
        self.assertEqual(result, expectation)


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
            launch(["-b", "-q", "tests/testdata/empty"])
        the_exception = cm.exception  
        self.assertEqual(the_exception.code, 1)

    def testRecursiveEmpty(self):
        # it should exit with code 2, because files are found but they
        # are not audiofiles
        with self.assertRaises(SystemExit) as cm:
            launch(["-b", "-r", "-q", "tests/testdata/empty"])
        the_exception = cm.exception  
        self.assertEqual(the_exception.code, 2)

    def testRecursiveAudio(self):
        # it should convert
        launch([
            "-b", "tests/testdata/audio",
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
            "-b", "tests/testdata/audio", "tests/testdata/audio/a.wav", "tests/testdata/empty",
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
        os.makedirs("tests/tmp", exist_ok=True)
        
    def tearDown(self):
        win[0].close()
        reset_settings()
        if os.path.isdir("tests/tmp/"):
            shutil.rmtree("tests/tmp")

    def testConversion(self):
        launch(["-q", "tests/testdata/audio/a.wav", "tests/testdata/audio/", "tests/testdata/empty"])
        window = win[0]

        # check if directory is read correctly
        expectation = ["tests/testdata/audio/a.wav", "tests/testdata/audio/b/c.mp3"]
        self.assertCountEqual([filename_to_uri(path) for path in expectation], win[0].filelist.filelist)

        # setup for conversion
        window.prefs.change_mime_type('audio/ogg; codecs=opus')
        window.prefs.settings.set_boolean('create-subfolders', False)
        window.prefs.settings.set_boolean('same-folder-as-input', False)
        window.prefs.settings.set_string('selected-folder', os.path.abspath("tests/tmp"))

        # start conversion
        window.on_convert_button_clicked()

        # wait for the assertions until all files are converted
        while window.converter.finished_tasks < len(expectation):
            # as Gtk.main is replaced by gtk_iteration, the unittests
            # are responsible about when soundconverter continues
            # to work on the conversions and updating the gui
            gtk_iteration()

        self.assertTrue(os.path.isdir("tests/tmp/audio/"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/a.opus"))
        self.assertTrue(os.path.isfile("tests/tmp/audio/b/c.opus"))
        # no duplicates in the gui:
        self.assertFalse(os.path.isfile("tests/tmp/a.opus"))


class TargetNameGeneratorTestCases(unittest.TestCase):
    def setUp(self):
        self.g = TargetNameGenerator()
        self.g.exists = self.never_exists
        self.g.replace_messy_chars = True

        self.s = SoundFile("/path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })

    def tearDown(self):
        self.g = None
        self.s = None

    def never_exists(self, pathname):
        return False

    def always_exists(self, pathname):
        return True

    def testSuffix(self):
        self.g.suffix = ".ogg"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")

    def testNoSuffix(self):
        try:
            self.g.get_target_name(self.s)
        except AssertionError:
            return  # ok
        assert False

    def testNoExtension(self):
        self.g.suffix = ".ogg"
        self.s = SoundFile("/path/to/file")
        self.assertEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")

    def testBasename(self):
        self.g.suffix = ".ogg"
        self.g.basename = "%(track-number)02d-%(title)s"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/path/to/01-Hi_Ho.ogg")

    def testLocation(self):
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.subfolders = "%(artist)s/%(album)s"
        self.g.basename = "%(track-number)02d-%(title)s"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg")

    def testLocationEscape(self):
        self.s = SoundFile("/path/to/file with spaces")
        self.g.replace_messy_chars = False
        self.g.suffix = ".ogg"
        self.g.folder = "/mu sic"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/mu%20sic/file%20with%20spaces.ogg")

    def testURI(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        #self.g.folder = "/")

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(self.g.get_target_name(self.s),
                             "ssh:user@server:port///path/to/file.ogg")

    def testURILocalDestination(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "/music"

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(self.g.get_target_name(self.s),
                             "/music/file.ogg")

    def testURIDistantDestination(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:/music/"

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/music/file.ogg")

    def testURIUnicode(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh:user@server:port" + quote(
            "///path/to/file with \u041d chars.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/m%C3%BBs%C3%AEc/file%20with%20%D0%9D%20chars.ogg")

    def testURIUnicode_utf8(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh:user@server:port" + quote(
            "///path/to/file with strângë chàrs фズ.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:" + quote(
                                 "/mûsîc/file with strângë chàrs фズ.ogg"))

    def testURIUnicodeMessy(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")

        self.s = SoundFile("ssh:user@server:port" + quote(
            "///path/to/file with strângë chàrs.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/" + quote(
                                 "mûsîc") + "/file_with_strange_chars.ogg")

    def testDisplay(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        #self.g.folder = "/")

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.assertEqual(self.s.filename_for_display,
                             "file.flac")
        self.s = SoundFile("ssh:user@server:port///path/to/fîlé.flac")
        self.assertEqual(self.s.filename_for_display,
                             "fîlé.flac")
        self.s = SoundFile(
            "ssh:user@server:port///path/to/fileфズ.flac")
        self.assertEqual(self.s.filename_for_display, "fileфズ.flac")

    def test8bits(self):
        self.s = SoundFile(quote("/path/to/file\xa0\xb0\xc0\xd0.flac"))
        self.g.suffix = ".ogg"
        self.g.replace_messy_chars = False
        self.assertEqual(self.g.get_target_name(self.s),
                             quote("/path/to/file\xa0\xb0\xc0\xd0.ogg"))

    def test8bits_messy(self):
        self.s = SoundFile(quote("/path/to/file\xa0\xb0\xc0\xd0.flac"))
        self.g.suffix = ".ogg"
        self.g.replace_messy_chars = True
        self.assertEqual(self.g.get_target_name(self.s),
                             "/path/to/file_A.ogg")


    def test8bits_tags(self):
        self.g.replace_messy_chars = False
        self.s = SoundFile("/path/to/fileyop.flac")
        self.s.tags.update({
            "artist": "\xa0\xb0\xc0\xd0",
            "title": "\xa1\xb1\xc1\xd1",
            "album": "\xa2\xb2\xc2\xd2",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.subfolders = "%(artist)s/%(album)s"
        self.g.basename = "%(title)s"
        self.assertEqual(self.g.get_target_name(self.s),
                             quote(
                                 "/music/\xa0\xb0\xc0\xd0/\xa2\xb2\xc2\xd2/\xa1\xb1\xc1\xd1.ogg"))


    def testRoot(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")


    def testRootPath(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        #self.g.basename = "%(title)s")
        self.assertEqual(self.g.get_target_name(self.s),
                             "/music/to/file.ogg")

    def testRootCustomPattern(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.basename = "%(title)s"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/path/to/Hi_Ho.ogg")

    def testRootPathCustomPattern(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.basename = "%(title)s"
        self.assertEqual(self.g.get_target_name(self.s),
                             "/music/to/Hi_Ho.ogg")

    def testQuote(self):
        self.s = SoundFile(quote("/path%'#/to/file%'#.flac"))
        self.s.tags.update({
            "artist": "Foo%'#Bar",
            "title": "Hi%'#Ho",
        })
        self.g.replace_messy_chars = False
        self.g.suffix = ".ogg"
        self.assertEqual(self.g.get_target_name(self.s),
                             quote("/path%'#/to/file%'#.ogg"))
        self.g.subfolders = "%(artist)s"
        self.g.basename = "%(title)s"
        self.assertEqual(self.g.get_target_name(self.s),
                             quote("/path%'#/to/Foo%'#Bar/Hi%'#Ho.ogg"))


if __name__ == "__main__":
    unittest.main()
