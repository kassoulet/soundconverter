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
from gi.repository import Gtk, GLib, Gst, GObject
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

from soundconverter.util.settings import get_gio_settings, settings
from soundconverter.util.formats import get_quality, get_file_extension
from soundconverter.util.fileoperations import filename_to_uri
from soundconverter.util.soundfile import SoundFile
from soundconverter.interface.ui import win, gtk_iteration, encoders
from soundconverter.interface.batch import cli_convert
from soundconverter.gstreamer.converter import available_elements
from soundconverter.gstreamer.discoverer import Discoverer

from util import reset_settings


original_available_elements = available_elements.copy()


def launch(argv=None, bin_path='bin/soundconverter'):
    """Start the soundconverter with the command line argument array argv.

    The batch mode is synchronous since it iterates the loop itself until
    finished.
    """
    # the tests should wait until the queues are done, so the sleep
    # can be omitted to speed them up.
    settings['gtk_close_sleep'] = 0

    if not argv:
        argv = []

    with patch.object(sys, 'argv', [''] + [str(arg) for arg in argv]):
        loader = SourceFileLoader('launcher', bin_path)
        spec = spec_from_loader('launcher', loader)
        spec.loader.exec_module(module_from_spec(spec))


def quote(ss):
    if isinstance(ss, str):
        ss = ss.encode('utf-8')
    return urllib.parse.quote(ss)


cwd = os.getcwd()


class BatchIntegration(unittest.TestCase):
    @classmethod
    def setUp(cls):
        os.makedirs('tests/tmp', exist_ok=True)

    def tearDown(self):
        # tests may change the cwd
        os.chdir(cwd)
        reset_settings()
        if os.path.isdir('tests/tmp/'):
            shutil.rmtree('tests/tmp')
        available_elements.update(original_available_elements)

    def test_single_file_m4a(self):
        launch([
            '-b', 'tests/test data/audio/a.wav',
            '-o', 'tests/tmp/64',
            '-f', 'm4a', '-q', '64'
        ])
        launch([
            '-b', 'tests/test data/audio/a.wav',
            '-o', 'tests/tmp/320',
            '-f', 'm4a', '-q', '320'
        ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        self.assertTrue(os.path.isfile('tests/tmp/320/a.m4a'))
        self.assertTrue(os.path.isfile('tests/tmp/64/a.m4a'))
        size_320 = os.path.getsize('tests/tmp/320/a.m4a')
        size_64 = os.path.getsize('tests/tmp/64/a.m4a')
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
        launch([
            '-b',
            'tests/test data/audio/a.wav',
            '-o', 'tests/tmp/8',
            '-f', 'mp3',
            '-m', 'vbr',
            '-q', 8  # smaller
        ])
        launch([
            '-b',
            'tests/test data/audio/a.wav',
            '-o', 'tests/tmp/2',
            '-f', 'mp3',
            '-m', 'vbr',
            '-q', 2
        ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        self.assertTrue(os.path.isfile('tests/tmp/8/a.mp3'))
        self.assertTrue(os.path.isfile('tests/tmp/2/a.mp3'))
        size_8 = os.path.getsize('tests/tmp/8/a.mp3')
        size_2 = os.path.getsize('tests/tmp/2/a.mp3')
        # it should be significantly smaller
        self.assertLess(size_8, size_2 / 2)
        # fails to read bitrate of vbr:
        self.assertEqual(
            self.get_bitrate('tests/tmp/2/a.mp3'),
            0
        )

    def test_abr(self):
        launch([
            '-b',
            'tests/test data/audio/a.wav',
            '-o', 'tests/tmp/320',
            '-f', 'mp3',
            '-m', 'abr',
            '-q', 320
        ])
        launch([
            '-b',
            'tests/test data/audio/a.wav',
            '-o', 'tests/tmp/112',
            '-f', 'mp3',
            '-m', 'abr',
            '-q', 112
        ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        self.assertTrue(os.path.isfile('tests/tmp/320/a.mp3'))
        self.assertTrue(os.path.isfile('tests/tmp/112/a.mp3'))
        size_320 = os.path.getsize('tests/tmp/320/a.mp3')
        size_112 = os.path.getsize('tests/tmp/112/a.mp3')
        self.assertLess(size_112, size_320 / 2)
        # fails to read bitrate of abr:
        self.assertEqual(
            self.get_bitrate('tests/tmp/112/a.mp3'),
            0
        )

    def test_cbr(self):
        launch([
            '-b',
            'tests/test data/audio/a.wav',
            '-o', 'tests/tmp',
            '-f', 'mp3',
            '-m', 'cbr',
            '-q', 256
        ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        self.assertTrue(os.path.isfile('tests/tmp/a.mp3'))
        self.assertEqual(
            self.get_bitrate('tests/tmp/a.mp3'),
            256
        )

    def test_non_recursive_with_folder(self):
        # it should exit with code 1, because no files are supplied
        with self.assertRaises(SystemExit) as ctx:
            launch([
                '-b', 'tests/test data/empty',
                '-f', 'mp3',
                '-o', 'tmp'
            ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], False)
        exit_code = ctx.exception.code
        self.assertEqual(exit_code, 1)

    def test_recursive_empty(self):
        # it should exit with code 2, because files are found but they
        # are not audio files
        with self.assertRaises(SystemExit) as cm:
            launch([
                '-b', '-r', 'tests/test data/empty',
                '-f', 'mp3',
                '-o', 'tmp',
                '-d'
            ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], True)
        self.assertEqual(settings['recursive'], True)
        the_exception = cm.exception
        self.assertEqual(the_exception.code, 2)

    def test_recursive_audio(self):
        # it should convert
        launch([
            '-b', 'tests/test data/audio',
            '-r',
            '-o', 'tests/tmp',
            '-f', 'wav',
            '-q', 24
        ])
        self.assertEqual(settings['main'], 'batch')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], True)
        self.assertTrue(os.path.isdir('tests/tmp/audio/'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/a.wav'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/b/c.wav'))

        # mono
        bitrate = self.get_bitrate('tests/tmp/audio/b/c.wav')
        self.assertEqual(bitrate, 44100 * 24 / 1000)

        # stereo
        bitrate = self.get_bitrate('tests/tmp/audio/a.wav')
        self.assertEqual(bitrate, 44100 * 24 / 1000 * 2)

    def test_multiple_paths(self):
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
        self.assertEqual(settings['main'], 'batch')
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

        # since the converison is done, the remaining time should stay
        # constant
        conversion_queue = cli_convert[0].conversions
        remaining_before = conversion_queue.get_remaining()
        time.sleep(0.01)
        remaining_after = conversion_queue.get_remaining()
        self.assertEqual(remaining_before, remaining_after)

    def test_tags(self):
        # it should run and not raise exceptions
        launch([
            '-t',
            'tests/test data/',
            '-r'
        ])
        self.assertEqual(settings['main'], 'tags')
        self.assertEqual(settings['debug'], False)
        self.assertEqual(settings['recursive'], True)

    def test_single_subdir_input(self):
        os.chdir('tests')
        # at some point this did not work, keep this spec even if it doesn't
        # appear to add value over test_recursive_audio
        launch([
            '-b',
            'test data', '-r',
            '-f', 'flac',
            '-o', 'tmp'
        ], '../bin/soundconverter')
        # the input directory is part of the output
        self.assertTrue(os.path.isdir('tmp/test data/audio/'))
        self.assertTrue(os.path.isfile('tmp/test data/audio/a.flac'))
        self.assertTrue(os.path.isfile('tmp/test data/audio/b/c.flac'))

    def test_pattern_1(self):
        launch([
            '-b', 'tests/test data/audio/',
            '-r',
            '-o', 'tests/tmp',
            '-p', '/{artist}/{album}',
            '-f', 'm4a'
        ])
        # since pattern is used, the "audio" part of the input path
        # is omitted and not reconstructed. e.g. "audio" might also be an
        # album name, in which case the old structure should be replaced
        # with the provided one.
        self.assertTrue(os.path.isfile(
            'tests/tmp/test_artist/test_album.m4a'
        ))
        self.assertTrue(os.path.isfile(
            'tests/tmp/Unknown Artist/Unknown Album.m4a'
        ))

    def test_pattern_2(self):
        launch([
            '-b',
            'tests/test data/audio/b/c.mp3',
            'tests/test data/audio/a.wav',
            '-r',
            '-o', 'tests/tmp',
            '-p', '{Artist}/{bar}/{filename}',
            '-f', 'm4a'
        ])
        self.assertTrue(os.path.isfile(
            'tests/tmp/test_artist/Unknown Bar/c.m4a'
        ))
        self.assertTrue(os.path.isfile(
            'tests/tmp/Unknown Artist/Unknown Bar/a.m4a'
        ))

    def test_skip_overwrite(self):
        path = 'tests/tmp/c.m4a'
        now = time.time()

        os.system('touch -d "2 hours ago" {}'.format(path))
        time_1 = os.path.getmtime(path)
        size_1 = os.path.getsize(path)
        # an empty file from 2 hours ago
        self.assertLess(abs(time_1 - (now - 60 * 60 * 2)), 10)
        self.assertEqual(size_1, 0)

        launch([
            '-b', 'tests/test data/audio/b/c.mp3',
            '-o', 'tests/tmp',
            '-f', 'm4a',
            '-e', 'skip'
        ])
        time_2 = os.path.getmtime(path)
        size_2 = os.path.getsize(path)
        # unchanged
        self.assertEqual(size_2, size_1)
        self.assertEqual(time_2, time_1)
        self.assertTrue(os.path.isfile(path))

        launch([
            '-b', 'tests/test data/audio/b/c.mp3',
            '-o', 'tests/tmp',
            '-f', 'm4a',
            '-e', 'overwrite'
        ])
        time_3 = os.path.getmtime(path)
        size_3 = os.path.getsize(path)
        # larger and newer file
        self.assertGreater(size_3, size_2)
        self.assertLess(abs(time_3 - now), 10)

    def test_increment_1(self):
        for _ in range(3):
            launch([
                '-b', 'tests/test data/audio/b/c.mp3',
                '-o', 'tests/tmp',
                '-f', 'm4a',
                '-e', 'increment'
            ])
        self.assertTrue(os.path.isfile('tests/tmp/c.m4a'))
        self.assertTrue(os.path.isfile('tests/tmp/c (1).m4a'))
        self.assertTrue(os.path.isfile('tests/tmp/c (2).m4a'))

    def test_increment_2(self):
        # increments by default
        for _ in range(3):
            launch([
                '-b', 'tests/test data/audio/b/c.mp3',
                '-o', 'tests/tmp',
                '-f', 'm4a'
            ])
        self.assertTrue(os.path.isfile('tests/tmp/c.m4a'))
        self.assertTrue(os.path.isfile('tests/tmp/c (1).m4a'))
        self.assertTrue(os.path.isfile('tests/tmp/c (2).m4a'))

    def test_set_delete_original_false(self):
        gio_settings = get_gio_settings()
        gio_settings.set_boolean('delete-original', True)
        gio_settings = get_gio_settings()
        self.assertTrue(gio_settings.get_boolean('delete-original'))
        launch([
            '-b', 'tests/test data/audio/b/c.mp3',
            '-o', 'tests/tmp',
            '-f', 'm4a'
        ])
        gio_settings = get_gio_settings()
        self.assertFalse(gio_settings.get_boolean('delete-original'))


class GUI(unittest.TestCase):
    def setUp(self):
        # reset quality settings, since they may be invalid for the ui mode
        # (e.g. an aribtrary mp3 quality of 200 does not exist for the ui)
        gio_settings = get_gio_settings()
        gio_settings.set_int('mp3-abr-quality', get_quality('audio/mpeg', -1, 'abr'))
        gio_settings.set_int('mp3-vbr-quality', get_quality('audio/mpeg', -1, 'vbr'))
        gio_settings.set_int('mp3-cbr-quality', get_quality('audio/mpeg', -1, 'cbr'))
        gio_settings.set_int('opus-bitrate', get_quality('audio/ogg; codecs=opus', -1))
        gio_settings.set_int('aac-quality', get_quality('audio/x-m4a', -1))
        gio_settings.set_double('vorbis-quality', get_quality('audio/x-vorbis', -1))
        gio_settings.set_boolean('delete-original', False)

        # conversion setup
        selected_folder = filename_to_uri('tests/tmp')
        gio_settings.set_string('selected-folder', selected_folder)
        gio_settings.set_boolean('create-subfolders', False)
        gio_settings.set_boolean('same-folder-as-input', False)
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
        available_elements.update(original_available_elements)

    def test_conversion_simple(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int(
            'opus-bitrate',
            get_quality('audio/ogg; codecs=opus', 3)
        )

        launch([
            'tests/test data/audio/a.wav'
        ])
        self.assertEqual(settings['main'], 'gui')
        window = win[0]

        # setup for conversion
        window.prefs.change_mime_type('audio/ogg; codecs=opus')
        # start conversion
        window.on_convert_button_clicked()

        # wait for the assertions until all files are converted
        queue = window.converter_queue
        while not queue.finished:
            # as Gtk.main is replaced by gtk_iteration, the unittests
            # are responsible about when soundconverter continues
            # to work on the conversions and updating the GUI
            gtk_iteration()

        self.assertTrue(os.path.isdir('tests/tmp/'))
        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))

    def test_conversion(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int(
            'opus-bitrate',
            get_quality('audio/ogg; codecs=opus', 3)
        )

        launch([
            'tests/test data/audio/a.wav',
            'tests/test data/audio/strângë chàrs фズ.wav',
            'tests/test data/audio/',
            'tests/test data/empty'
        ])
        self.assertEqual(settings['main'], 'gui')
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

        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        window.on_convert_button_clicked()

        queue = window.converter_queue

        first_conversion = queue.all_tasks[0]
        first_bus = first_conversion.pipeline.get_bus()
        # is listening for messages
        self.assertTrue(GObject.signal_handler_is_connected(
            first_bus,
            first_conversion.watch_id
        ))

        pipeline = queue.all_tasks[0].pipeline

        # wait for the assertions until all files are converted
        while not queue.finished:
            gtk_iteration()

        self.assertEqual(len(queue.all_tasks), 3)
        self.assertTrue(queue.all_tasks[0].done)
        self.assertTrue(queue.all_tasks[1].done)
        self.assertTrue(queue.all_tasks[2].done)
        self.assertEqual(queue.all_tasks[0].get_progress()[0], 1)
        self.assertEqual(queue.all_tasks[1].get_progress()[0], 1)
        self.assertEqual(queue.all_tasks[2].get_progress()[0], 1)

        # (total_progress, [(sound_file, progress), ...])
        self.assertEqual(queue.get_progress()[0], 1)
        self.assertEqual(queue.get_progress()[1][0][1], 1)
        self.assertEqual(queue.get_progress()[1][1][1], 1)
        self.assertEqual(queue.get_progress()[1][2][1], 1)
        self.assertIs(queue.get_progress()[1][0][0], queue.all_tasks[0])
        self.assertIs(queue.get_progress()[1][1][0], queue.all_tasks[1])
        self.assertIs(queue.get_progress()[1][2][0], queue.all_tasks[2])

        self.assertIsNotNone(queue.all_tasks[0].sound_file.duration)
        self.assertIsNotNone(queue.all_tasks[1].sound_file.duration)
        self.assertIsNotNone(queue.all_tasks[2].sound_file.duration)

        duration = queue.get_duration()
        time.sleep(0.05)
        # The duration may not increase by 0.05 seconds, because it's finished
        self.assertLess(abs(queue.get_duration() - duration), 0.001)

        self.assertEqual(len(queue.done), len(expected_filelist))

        # 'tests/test data/empty' causes the commonprefix to be everything
        # up to 'audio', hence an 'audio' folder is created
        self.assertTrue(os.path.isdir('tests/tmp/audio/'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/a.opus'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/strange_chars_.opus'))
        self.assertTrue(os.path.isfile('tests/tmp/audio/b/c.opus'))
        # no duplicates in the GUI:
        self.assertFalse(os.path.isfile('tests/tmp/a.opus'))

        errors = sum([1 for task in queue.done if task.error])
        self.assertEqual(errors, 0)
        self.assertNotIn('error', window.statustext.get_text())
        self.assertFalse(window.filelist.progress_column.get_visible())

        self.assertEqual(len(window.filelist.invalid_files_list), 2)
        self.assertIn('empty/a', window.filelist.invalid_files_list)
        self.assertIn('empty/b/c', window.filelist.invalid_files_list)

        # cleans up at the end. Important because otherwise it will crash
        # because too many files are open.
        self.assertEqual(pipeline.get_state(0).state, Gst.State.NULL)
        self.assertIsNone(queue.all_tasks[0].pipeline)

        # correctly stops listening for messages to avoid a leakage of
        # open fds https://bugs.launchpad.net/soundconverter/+bug/1928210
        self.assertFalse(GObject.signal_handler_is_connected(
            first_bus,
            first_conversion.watch_id
        ))

    def test_pause_resume(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int(
            'opus-bitrate',
            get_quality('audio/ogg; codecs=opus', 3)
        )

        launch([
            'tests/test data/audio/a.wav'
        ])
        self.assertEqual(settings['main'], 'gui')
        self.assertEqual(settings['debug'], False)

        window = win[0]

        expected_filelist = [
            'tests/test data/audio/a.wav'
        ]
        self.assertCountEqual(
            [filename_to_uri(path) for path in expected_filelist],
            win[0].filelist.filelist
        )

        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        window.on_convert_button_clicked()

        queue = window.converter_queue
        self.assertEqual(len(queue.running), 1)
        self.assertEqual(len(queue.done), 0)
        self.assertEqual(queue.pending.qsize(), 0)
        Gtk.main_iteration()

        window.on_button_pause_clicked()  # pause

        duration = queue.get_duration()
        # my computer needs ~0.03 seconds to convert it. So sleep some
        # significantly longer time than that to make sure pause actually
        # pauses the conversion.
        time.sleep(0.5)
        gtk_iteration()
        self.assertTrue(window.filelist.progress_column.get_visible())
        self.assertEqual(len(queue.running), 1)
        self.assertEqual(len(queue.done), 0)
        self.assertEqual(queue.pending.qsize(), 0)
        self.assertLess(abs(queue.get_duration() - duration), 0.001)
        self.assertFalse(os.path.isfile('tests/tmp/a.opus'))

        window.on_button_pause_clicked()  # resume

        start = time.time()
        while not queue.finished:
            gtk_iteration()
        if time.time() - start > 0.4:
            print(
                'The test may not work as intended because the conversion'
                'may take longer than the pause duration.'
            )

        self.assertEqual(len(queue.running), 0)
        self.assertEqual(len(queue.done), 1)
        self.assertEqual(queue.pending.qsize(), 0)
        self.assertGreater(queue.get_duration(), duration)
        self.assertEqual(queue.get_progress()[0], 1)

        converter_queue = window.converter_queue
        self.assertEqual(len(converter_queue.done), len(expected_filelist))

        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))

        errors = sum([1 for task in converter_queue.done if task.error])
        self.assertEqual(errors, 0)
        self.assertNotIn('error', window.statustext.get_text())
        self.assertFalse(window.filelist.progress_column.get_visible())
        self.assertEqual(len(window.filelist.invalid_files_list), 0)

    def test_cancel(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int(
            'opus-bitrate',
            get_quality('audio/ogg; codecs=opus', 3)
        )

        launch([
            'tests/test data/audio/a.wav'
        ])
        self.assertEqual(settings['main'], 'gui')
        self.assertEqual(settings['debug'], False)

        window = win[0]

        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        window.on_convert_button_clicked()
        gtk_iteration(True)
        queue = window.converter_queue
        pipeline = queue.all_tasks[0].pipeline

        # quick check if the conversion correctly started
        self.assertEqual(len(queue.running), 1)
        pipeline_state = pipeline.get_state(Gst.CLOCK_TIME_NONE).state
        self.assertEqual(pipeline_state, Gst.State.PLAYING)

        window.on_button_cancel_clicked()

        # the task should not be running anymore
        self.assertEqual(len(queue.running), 0)
        # the running task is put back into pending
        self.assertEqual(queue.pending.qsize(), 1)
        pipeline_state = pipeline.get_state(Gst.CLOCK_TIME_NONE).state
        self.assertEqual(pipeline_state, Gst.State.NULL)

        # my computer needs ~0.03 seconds to convert it. So sleep some
        # significantly longer time than that to make sure cancel actually
        # cancels the conversion.
        time.sleep(0.5)
        gtk_iteration()
        self.assertFalse(window.filelist.progress_column.get_visible())
        self.assertEqual(len(queue.running), 0)
        self.assertEqual(len(queue.done), 0)
        self.assertEqual(queue.pending.qsize(), 1)
        self.assertFalse(os.path.isfile('tests/tmp/a.opus'))
        pipeline_state = pipeline.get_state(Gst.CLOCK_TIME_NONE).state
        self.assertEqual(pipeline_state, Gst.State.NULL)

        window.on_convert_button_clicked()
        gtk_iteration(True)
        new_queue = window.converter_queue
        new_pipeline = new_queue.all_tasks[0].pipeline

        # the new queue is running now instead
        self.assertEqual(len(new_queue.running), 1)
        new_pipeline_state = new_pipeline.get_state(Gst.CLOCK_TIME_NONE).state
        self.assertEqual(new_pipeline_state, Gst.State.PLAYING)
        # the old one is not running
        old_pipeline_state = pipeline.get_state(Gst.CLOCK_TIME_NONE).state
        self.assertEqual(old_pipeline_state, Gst.State.NULL)
        self.assertEqual(len(queue.running), 0)
        self.assertEqual(queue.pending.qsize(), 1)

        gtk_iteration()
        self.assertTrue(window.filelist.progress_column.get_visible())

        start = time.time()
        while not new_queue.finished:
            gtk_iteration()
        if time.time() - start > 0.4:
            print(
                'The test may not work as intended because the conversion'
                'may take longer than the cancel duration.'
            )

        # the old queue object didn't finish anything
        self.assertEqual(len(queue.done), 0)
        self.assertEqual(queue.pending.qsize(), 1)

        # the new queue finished
        self.assertEqual(len(new_queue.running), 0)
        self.assertEqual(len(new_queue.done), 1)
        self.assertEqual(new_queue.pending.qsize(), 0)
        self.assertEqual(new_queue.get_progress()[0], 1)
        self.assertEqual(new_pipeline.get_state(0).state, Gst.State.NULL)

        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))

    def test_conversion_pattern(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('aac-quality', get_quality('audio/x-m4a', 3))

        gio_settings.set_int('name-pattern-index', -1)
        filename_pattern = '{Title}/f o'
        gio_settings.set_string('custom-filename-pattern', filename_pattern)

        gio_settings.set_boolean('create-subfolders', True)
        gio_settings.set_int('subfolder-pattern-index', 0)

        gio_settings.set_boolean('replace-messy-chars', False)

        launch([
            'tests/test data/audio/a.wav',
            'tests/test data/audio/strângë chàrs фズ.wav',
            'tests/test data/audio/',
            'tests/test data/empty',
            '--debug'
        ])
        self.assertEqual(settings['debug'], True)

        window = win[0]

        # setup for conversion. mp4mux was not sending tag messages, so
        # make sure that tags from the discovery are properly used in the
        # conversion
        window.prefs.change_mime_type('audio/x-m4a')

        window.on_convert_button_clicked()

        queue = window.converter_queue
        while not queue.finished:
            gtk_iteration()

        # input files should not have been deleted
        self.assertTrue(os.path.isfile(
            'tests/test data/audio/a.wav'
        ))
        self.assertTrue(os.path.isfile(
            'tests/test data/audio/strângë chàrs фズ.wav'
        ))

        self.assertTrue(os.path.isdir('tests/tmp/'))
        self.assertTrue(os.path.isfile(
            'tests/tmp/Unknown Artist/Unknown Album/a/f o.m4a'
        ))
        self.assertTrue(os.path.isfile(
            'tests/tmp/Unknown Artist/Unknown Album/strângë chàrs '
            'фズ/f o.m4a'
        ))
        self.assertTrue(os.path.isfile(
            'tests/tmp/test_artist/test_album/c/f o.m4a'
        ))

    def test_non_overwriting(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int(
            'opus-bitrate',
            get_quality('audio/ogg; codecs=opus', 3)
        )

        launch([
            'tests/test data/audio/a.wav'
        ])
        self.assertEqual(settings['main'], 'gui')
        window = win[0]

        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        # create a few duplicates
        for _ in range(3):
            window.on_convert_button_clicked()
            queue = window.converter_queue
            while not queue.finished:
                gtk_iteration()

        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))
        self.assertTrue(os.path.isfile('tests/tmp/a_(1).opus'))
        self.assertTrue(os.path.isfile('tests/tmp/a_(2).opus'))

    def test_delete_original(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int(
            'opus-bitrate',
            get_quality('audio/ogg; codecs=opus', 3)
        )
        gio_settings.set_boolean('delete-original', True)

        os.system('cp "tests/test data/audio/a.wav" "tests/tmp/a.wav"')
        self.assertTrue(os.path.isfile('tests/tmp/a.wav'))

        launch([
            'tests/tmp/a.wav'
        ])
        self.assertEqual(settings['main'], 'gui')
        window = win[0]

        window.prefs.change_mime_type('audio/ogg; codecs=opus')

        window.on_convert_button_clicked()
        queue = window.converter_queue
        while not queue.finished:
            gtk_iteration()

        self.assertTrue(os.path.isfile('tests/tmp/a.opus'))

        # should have been deleted
        self.assertFalse(os.path.isfile('tests/tmp/a.wav'))

    def test_missing_plugin(self):
        gio_settings = get_gio_settings()

        # delete the second element in the list of available encoders,
        # in order to test how the higher indexes behave. Selecting any
        # format row on the ui should still properly match to the right
        # encoder.
        mime_to_delete, encoder_to_delete, _ = encoders[1]
        selected_index = 2
        mime_to_select = encoders[selected_index][0]
        # index 1 is currently (and will most likely stay) lamemp3enc.
        # Test doesn't support multiple options like in m4a (faac,avenc_aac)
        # currently. If needed rewrite this.
        self.assertNotIn(',', encoder_to_delete)
        # This should trigger deleting the mp3 element from the dropdown
        # in set_widget_initial_values:
        available_elements.remove(encoder_to_delete)

        launch()
        window = win[0]

        extension_to_delete = get_file_extension(mime_to_delete).lower()
        for row in window.prefs.liststore8:
            if extension_to_delete in row[0].lower():
                raise AssertionError(
                    'Expected {} to be missing'.format(extension_to_delete)
                )

        window.prefs.output_mime_type.set_active(selected_index)

        # indexes should all map to each other properly without having to
        # modify `encoders`.
        self.assertEqual(
            gio_settings.get_string('output-mime-type'),
            mime_to_select
        )

    def test_non_audio(self):
        # launch a window, insert a folder containing empty files, check
        # list of non-audio files, check conversion output
        launch()
        window = win[0]
        window.filelist.add_uris([
            'file:///' + os.path.realpath('tests/test%20data')
        ])

        while window.filelist.discoverers is None:
            gtk_iteration()

        discoverer_queue = window.filelist.discoverers
        while not discoverer_queue.finished:
            gtk_iteration()

        self.assertIn('test data/empty/b/c', window.filelist.invalid_files_list)
        self.assertIn('test data/empty/a', window.filelist.invalid_files_list)
        self.assertIn('test data/a.iso', window.filelist.invalid_files_list)

        # due to the dialog being opened with .run, it would be blocking in
        # a new main loop until the close button is clicked by hand (see
        # https://lazka.github.io/pgi-docs/#Gtk-3.0/classes/Dialog.html)
        # so add closing the dialog to pending events.
        # Using .show instead of .run would probably work fine as well.
        GLib.idle_add(lambda: window.showinvalid_dialog_closebutton.clicked())
        window.on_showinvalid_activate()

        text = window.showinvalid_dialog_list.get_buffer().props.text
        self.assertIn('test data/empty/b/c', text)
        self.assertIn('test data/empty/a', text)
        self.assertIn('test data/a.iso', text)

        window.prefs.change_mime_type('audio/mpeg')

        window.on_convert_button_clicked()
        queue = window.converter_queue
        while not queue.finished:
            gtk_iteration()

        # it uses the commonprefix of all files, not just the valid ones
        self.assertTrue(os.path.isfile('tests/tmp/test_data/audio/b/c.mp3'))
        self.assertTrue(os.path.isfile('tests/tmp/test_data/audio/a.mp3'))
        self.assertTrue(os.path.isfile(
            'tests/tmp/test_data/audio/strange_chars_.mp3'
        ))
        self.assertFalse(os.path.isfile('tests/tmp/test_data/empty/b/c'))
        self.assertFalse(os.path.isfile('tests/tmp/test_data/empty/a'))
        self.assertFalse(os.path.isfile('tests/tmp/test_data/a.iso'))

    def test_all_m4a_encoders(self):
        for encoder in ['fdkaacenc', 'faac', 'avenc_aac']:
            # create one large and one small file to test if the quality
            # setting is respected
            for quality_index in [0, 5]:
                launch([
                    'tests/test data/audio/a.wav'
                ])
                window = win[0]
                window.prefs.change_mime_type('audio/x-m4a')

                class FakeComboBox:
                    """Act like some quality is selected."""
                    def get_active(self):
                        return quality_index

                window.prefs.on_aac_quality_changed(FakeComboBox())

                get_gio_settings().set_string(
                    'selected-folder',
                    'file://' + os.path.realpath(
                        'tests/tmp/{}/{}'.format(encoder, quality_index)
                    )
                )

                available_elements.clear()
                available_elements.update({encoder, 'mp4mux'})
                window.on_convert_button_clicked()
                queue = window.converter_queue
                while not queue.finished:
                    gtk_iteration()
                win[0].close()

            path_5 = 'tests/tmp/{}/5/a.m4a'.format(encoder)
            path_0 = 'tests/tmp/{}/0/a.m4a'.format(encoder)
            self.assertTrue(path_5)
            self.assertTrue(path_0)
            size_5 = os.path.getsize(path_5)
            size_0 = os.path.getsize(path_0)
            self.assertLess(size_0, size_5)

    def test_ignores_example_name_errors(self):
        # https://bugs.launchpad.net/soundconverter/+bug/1934517
        def fail(*args):
            # make the constructor raise an error
            raise ValueError()

        init = 'soundconverter.util.namegenerator.TargetNameGenerator.__init__'
        with patch(init, fail):
            # won't crash because an error in update_example is not critical
            # enough
            launch()
            window = win[0]
            window.prefs.update_example()


if __name__ == '__main__':
    unittest.main()
