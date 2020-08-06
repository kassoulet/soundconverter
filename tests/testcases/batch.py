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
import urllib.parse

from soundconverter.interface.batch import prepare_files_list
from soundconverter.util.settings import settings
from soundconverter.util.fileoperations import vfs_exists


cwd = os.getcwd()


class BatchUtils(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def tearDown(self):
        # tests may change the cwd
        os.chdir(cwd)

    def test_prepare_files_list(self):
        settings['recursive'] = True
        parsed_files, subdirectories = prepare_files_list(['tests/test data/audio/b/'])
        self.assertListEqual(
            parsed_files,
            ['file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3')]
        )
        self.assertListEqual(
            subdirectories,
            ['b/']
        )

    def test_prepare_files_list_nonrecursive(self):
        settings['recursive'] = False
        parsed_files, subdirectories = prepare_files_list(['tests/test data/audio/b/'])
        self.assertEqual(len(parsed_files), 0)
        self.assertEqual(len(subdirectories), 0)

    def test_prepare_files_list_multiple(self):
        settings['recursive'] = True
        parsed_files, subdirectories = prepare_files_list(['tests/test data/audio/'])

        self.assertEqual(len(parsed_files), 3)
        self.assertIn('file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3'), parsed_files)
        self.assertIn('file://' + os.path.realpath('tests/test%20data/audio/a.wav'), parsed_files)
        self.assertIn('file://' + urllib.parse.quote(os.path.realpath('tests/test data/audio/strângë chàrs фズ.wav')), parsed_files)

        self.assertEqual(len(subdirectories), 3)
        self.assertIn('audio/b/', subdirectories)
        self.assertIn('audio/', subdirectories)
        self.assertIn('audio/', subdirectories)

    def test_two_dirs(self):
        settings['recursive'] = True
        parsed_files, subdirectories = prepare_files_list([
            'tests/test data/audio/',
            'tests/test data/empty/'
        ])
        expected_files = [
            'file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3'),
            'file://' + os.path.realpath('tests/test%20data/audio/a.wav'),
            'file://' + urllib.parse.quote(os.path.realpath('tests/test data/audio/strângë chàrs фズ.wav')),
            'file://' + os.path.realpath('tests/test%20data/empty/a'),
            'file://' + os.path.realpath('tests/test%20data/empty/b/c')
        ]
        for expected_file in expected_files:
            # make sure expected_files are correctly written
            self.assertTrue(
                vfs_exists(expected_file),
                'expected {} to exist'.format(expected_file)
            )

        expected_files.sort()
        parsed_files.sort()
        self.assertEqual(parsed_files, expected_files)

        expected_dirs = [
            'audio/b/',
            'audio/',
            'audio/',
            'empty/',
            'empty/b/'
        ]
        expected_dirs.sort()
        subdirectories.sort()
        self.assertEqual(subdirectories, expected_dirs)

    def test_single_dir_depth_input(self):
        settings['recursive'] = True
        os.chdir('tests')
        # at some point this did not work, keep this spec even if it doesn't
        # appear to add value over the other tests
        parsed_files, subdirectories = prepare_files_list(['test data'])

        expected_files = [
            'file://' + os.path.realpath('test%20data/audio/b/c.mp3'),
            'file://' + os.path.realpath('test%20data/audio/a.wav'),
            'file://' + urllib.parse.quote(os.path.realpath('test data/audio/strângë chàrs фズ.wav')),
            'file://' + os.path.realpath('test%20data/empty/a'),
            'file://' + os.path.realpath('test%20data/empty/b/c'),
            'file://' + os.path.realpath('test%20data/a.iso')
        ]
        for expected_file in expected_files:
            # make sure expected_files are correctly written
            self.assertTrue(
                vfs_exists(expected_file),
                'expected {} to exist'.format(expected_file)
            )

        expected_files.sort()
        parsed_files.sort()
        self.assertEqual(parsed_files, expected_files)

        expected_dirs = [
            'test data/audio/b/',
            'test data/audio/',
            'test data/audio/',
            'test data/empty/',
            'test data/empty/b/',
            'test data/'
        ]
        expected_dirs.sort()
        subdirectories.sort()
        self.assertEqual(subdirectories, expected_dirs)

    def test_absolute(self):
        settings['recursive'] = True
        parsed_files, subdirectories = prepare_files_list([os.path.realpath('tests/test data')])

        expected_files = [
            'file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3'),
            'file://' + os.path.realpath('tests/test%20data/audio/a.wav'),
            'file://' + urllib.parse.quote(os.path.realpath('tests/test data/audio/strângë chàrs фズ.wav')),
            'file://' + os.path.realpath('tests/test%20data/empty/a'),
            'file://' + os.path.realpath('tests/test%20data/empty/b/c'),
            'file://' + os.path.realpath('tests/test%20data/a.iso')
        ]
        expected_files.sort()
        parsed_files.sort()
        self.assertEqual(parsed_files, expected_files)

        expected_dirs = [
            'test data/audio/b/',
            'test data/audio/',
            'test data/audio/',
            'test data/empty/',
            'test data/empty/b/',
            'test data/'
        ]
        expected_dirs.sort()
        subdirectories.sort()
        self.assertEqual(subdirectories, expected_dirs)

    def test_files(self):
        settings['recursive'] = True
        parsed_files, subdirectories = prepare_files_list([
            'tests/test data/audio/b/c.mp3',
            'tests/test data/audio/a.wav'
        ])

        self.assertEqual(parsed_files, [
            'file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3'),
            'file://' + os.path.realpath('tests/test%20data/audio/a.wav')
        ])

        self.assertEqual(subdirectories, ['', ''])


if __name__ == "__main__":
    unittest.main()