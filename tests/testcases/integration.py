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
import time
import sys
import shutil
import urllib.parse
from gi.repository import Gio, Gtk
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

from soundconverter.util.settings import get_gio_settings, settings
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.formats import get_quality
from soundconverter.util.fileoperations import filename_to_uri
from soundconverter.interface.ui import win, gtk_iteration

from util import reset_settings


def launch(argv=[]):
    """Start the soundconverter with the command line argument array argv.

    The batch mode is synchronous (for some unknown reason), so after that
    you can start checking conversion results.
    """
    testargs = sys.argv.copy()[:1]
    testargs += argv
    with patch.object(sys, 'argv', testargs):
        loader = SourceFileLoader('launcher', 'bin/soundconverter')
        spec = spec_from_loader('launcher', loader)
        spec.loader.exec_module(module_from_spec(spec))


def quote(ss):
    if isinstance(ss, str):
        ss = ss.encode('utf-8')
    return urllib.parse.quote(ss)


class BatchIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs('tests/tmp', exist_ok=True)

    def tearDown(self):
        reset_settings()
        if os.path.isdir('tests/tmp/'):
            shutil.rmtree('tests/tmp')

    def testSingleFile(self):
        # it should convert
        launch([
            '-b',
            'tests/test data/audio/a.wav',
            '-o', 'tests/tmp',
            '-f', 'm4a'
        ])
        self.assertEqual(settings['mode'], 'batch')
        self.assertEqual(settings['quiet'], False)
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        self.assertTrue(os.path.isfile('tests/tmp/a.m4a'))

    def testNonRecursiveWithFolder(self):
        # it should exit with code 1, because no files are supplied
        with self.assertRaises(SystemExit) as ctx:
            launch([
                '-b', 'tests/test data/empty', '-f', 'audio/mpeg',
                '-o', 'tmp'
            ])
        self.assertEqual(settings['mode'], 'batch')
        self.assertEqual(settings['quiet'], False)
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        exit_code = ctx.exception.code
        self.assertEqual(exit_code, 1)

    def testRecursiveEmpty(self):
        # it should exit with code 2, because files are found but they
        # are not audio files
        with self.assertRaises(SystemExit) as cm:
            launch([
                '-b', '-r', 'tests/test data/empty', '-f', 'audio/mpeg',
                '-o', 'tmp',
                '-q', '-d'
            ])
        self.assertEqual(settings['mode'], 'batch')
        self.assertEqual(settings['quiet'], True)
        self.assertEqual(settings['debug'], True)
        self.assertEqual(settings['recursive'], True)
        the_exception = cm.exception
        self.assertEqual(the_exception.code, 2)

    def testRecursiveAudio(self):
        # it should convert
        launch([
            '-b', 'tests/test data/audio',
            '-r',
            '-o', 'tests/tmp',
            '-f', 'audio/mpeg',
            '-q'
        ])
        self.assertEqual(settings['mode'], 'batch')
        self.assertEqual(settings['quiet'], True)
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], True)
        self.assertTrue(os.path.isdir('tests/tmp/audio/'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/a.mp3'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/b/c.mp3'))

    def testMultiplePaths(self):
        # it should convert
        launch([
            '-b',
            'tests/test data/audio',
            'tests/test data/audio/a.wav',
            'tests/test data/empty',
            '-r',
            '-o', 'tests/tmp',
            '-f', 'opus',
            '-d'
        ])
        self.assertEqual(settings['mode'], 'batch')
        self.assertEqual(settings['quiet'], False)
        self.assertEqual(settings['debug'], True)
        self.assertEqual(settings['recursive'], True)
        # The batch mode behaves like the cp command:
        # - input is a folder, has to provide -r, output is a folder
        # - input is a file, output is a file
        self.assertTrue(os.path.isdir('tests/tmp/audio/'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/a.opus'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/b/c.opus'))
        # a.wav was provided twice, so here is it again but this time without
        # subfolder, just like the input.
        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))

    def testCheck(self):
        # it should run and not raise exceptions
        launch([
            '-c',
            'tests/test data/',
            '-r'
        ])
        self.assertEqual(settings['mode'], 'check')
        self.assertEqual(settings['quiet'], False)
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], True)

    def testTags(self):
        # it should run and not raise exceptions
        launch([
            '-t',
            'tests/test data/',
            '-r'
        ])
        self.assertEqual(settings['mode'], 'tags')
        self.assertEqual(settings['quiet'], False)
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], True)


class GUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # reset quality settings, since they may be invalid for the ui mode
        # (e.g. an aribtrary mp3 quality of 200 does not exist for the ui)
        gio_settings = get_gio_settings()
        gio_settings.set_int('mp3-abr-quality', get_quality('mp3', -1, 'abr'))
        gio_settings.set_int('mp3-vbr-quality', get_quality('mp3', -1, 'vbr'))
        gio_settings.set_int('mp3-cbr-quality', get_quality('mp3', -1, 'cbr'))
        gio_settings.set_int('opus-bitrate', get_quality('opus', -1))
        gio_settings.set_int('aac-quality', get_quality('aac', -1))
        gio_settings.set_double('vorbis-quality', get_quality('ogg', -1))

        # conversion setup
        gio_settings.set_boolean('create-subfolders', False)
        gio_settings.set_boolean('same-folder-as-input', False)
        selected_folder = filename_to_uri('tests/tmp')
        gio_settings.set_string('selected-folder', selected_folder)
        gio_settings.set_int('name-pattern-index', 0)
        gio_settings.set_boolean('replace-messy-chars', True)
        gio_settings.set_boolean('delete-original', False)

        if os.path.isdir('tests/tmp/'):
            shutil.rmtree('tests/tmp')
        os.makedirs('tests/tmp', exist_ok=True)

    def tearDown(self):
        win[0].close()
        reset_settings()
        if os.path.isdir('tests/tmp/'):
            shutil.rmtree('tests/tmp')

    def testConversion(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('opus-bitrate', get_quality('opus', 3))

        launch([
            'tests/test data/audio/a.wav',
            'tests/test data/audio/strângë chàrs фズ.wav',
            'tests/test data/audio/',
            'tests/test data/empty'
        ])
        self.assertEqual(settings['mode'], 'gui')
        window = win[0]

        # check if directory is read correctly
        expected_filelist = [
            'tests/test data/audio/a.wav',
            'tests/test data/audio/strângë chàrs фズ.wav',
            'tests/test data/audio/b/c.mp3'
        ]
        uris = [filename_to_uri(path) for path in expected_filelist]
        self.assertCountEqual(
            uris,
            win[0].filelist.filelist
        )
        for uri in uris:
            self.assertIn(uri, win[0].filelist.filelist)

        # setup for conversion
        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        # start conversion
        window.on_convert_button_clicked()

        # wait for the assertions until all files are converted
        queue = window.converter_queue
        converter = queue.running[0]
        sound_file = queue.running[0].sound_file
        while not queue.finished:
            # as Gtk.main is replaced by gtk_iteration, the unittests
            # are responsible about when soundconverter continues
            # to work on the conversions and updating the GUI
            gtk_iteration()
            print(
                window.filelist.model[sound_file.filelist_row][2],
                converter.get_progress()
            )

        duration = queue.get_duration()
        time.sleep(0.05)
        # The duration may not increase by 0.05 seconds, because it's finished
        self.assertLess(abs(queue.get_duration() - duration), 0.001)

        self.assertEqual(len(queue.done), len(expected_filelist))

        self.assertTrue(os.path.isdir('tests/tmp/audio/'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/a.opus'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/strange_chars_.opus'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/b/c.opus'))
        # no duplicates in the GUI:
        self.assertFalse(os.path.isfile('tests/tmp/a.opus'))

    def testPauseResume(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('opus-bitrate', get_quality('opus', 3))

        launch([
            'tests/test data/audio/a.wav'
        ])
        self.assertEqual(settings['mode'], 'gui')
        window = win[0]

        expected_filelist = [
            'tests/test data/audio/a.wav'
        ]
        self.assertCountEqual(
            [filename_to_uri(path) for path in expected_filelist],
            win[0].filelist.filelist
        )

        # setup for conversion
        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        # start conversion
        window.on_convert_button_clicked()
        queue = window.converter_queue
        converter = queue.running[0]
        sound_file = queue.running[0].sound_file
        self.assertEqual(len(queue.running), 1)
        self.assertEqual(len(queue.done), 0)
        self.assertEqual(queue.pending.qsize(), 0)
        gtk_iteration()

        window.on_button_pause_clicked()  # pause

        duration = queue.get_duration()
        # my computer needs ~0.03 seconds to convert it. So sleep some
        # significantly longer time than that to make sure pause actually
        # pauses the conversion.
        time.sleep(0.5)
        gtk_iteration()
        self.assertEqual(len(queue.running), 1)
        self.assertEqual(len(queue.done), 0)
        self.assertEqual(queue.pending.qsize(), 0)
        self.assertLess(abs(queue.get_duration() - duration), 0.001)
        self.assertFalse(os.path.isfile('tests/tmp/a.opus'))

        window.on_button_pause_clicked()  # resume

        start = time.time()
        while not queue.finished:
            gtk_iteration()
            print(
                window.filelist.model[sound_file.filelist_row][2],
                converter.get_progress()
            )
        if time.time() - start > 0.4:
            print(
                'The test may not work as intended because the conversion'
                'may take longer than the pause duration.'
            )

        self.assertEqual(len(queue.running), 0)
        self.assertEqual(len(queue.done), 1)
        self.assertEqual(queue.pending.qsize(), 0)
        self.assertGreater(queue.get_duration(), duration)
        self.assertEqual(queue.get_progress(), 1)

        converter_queue = window.converter_queue
        self.assertEqual(len(converter_queue.done), len(expected_filelist))

        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))

        self.assertEqual(window.filelist.model[sound_file.filelist_row][2], 1)


if __name__ == '__main__':
    unittest.main()
