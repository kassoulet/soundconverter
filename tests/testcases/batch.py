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

from soundconverter.interface.batch import prepare_files_list, \
    validate_args, use_memory_gsettings
from soundconverter.util.settings import settings, get_gio_settings
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
            'file://' + os.path.realpath('test%20data/a.iso'),
            'file://' + os.path.realpath('test%20data/no%20tags/no-tags.mp3'),
            'file://' + os.path.realpath('test%20data/no%20tags/no-tags.ogg'),
            'file://' + os.path.realpath('test%20data/no%20tags/no-tags.flac'),
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
            'test data/audio/',  # duplicate, because there are two files in there
            'test data/empty/',
            'test data/empty/b/',
            'test data/',
            'test data/no tags/',
            'test data/no tags/',
            'test data/no tags/'
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
            'file://' + os.path.realpath('tests/test%20data/a.iso'),
            'file://' + os.path.realpath('tests/test%20data/no%20tags/no-tags.mp3'),
            'file://' + os.path.realpath('tests/test%20data/no%20tags/no-tags.ogg'),
            'file://' + os.path.realpath('tests/test%20data/no%20tags/no-tags.flac'),
        ]
        expected_files.sort()
        parsed_files.sort()
        self.assertEqual(parsed_files, expected_files)

        expected_dirs = [
            'test data/audio/b/',
            'test data/audio/',
            'test data/audio/',  # duplicate, because there are two files in there
            'test data/empty/',
            'test data/empty/b/',
            'test data/',
            'test data/no tags/',
            'test data/no tags/',
            'test data/no tags/'
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

    def test_validate_args(self):
        # working example
        self.assertTrue(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'mp3', 'quality': 5
        }))
        # input and output
        self.assertFalse(validate_args({
            'main': 'batch', 'format': 'mp3',
            'mode': 'cbr', 'quality': 192
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '',
            'format': 'mp3', 'mode': 'cbr', 'quality': 192
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'mp3', 'quality': 5,
            'existing': 'abc'
        }))
        self.assertTrue(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'mp3', 'quality': 5,
            'existing': 'overwrite'
        }))
        # formats
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'quality': 5
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.', 'format': 'mp3',
            'quality': 192  # False because it defaults to vbr
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'mp3', 'mode': 'vbr', 'quality': 192
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'mp3', 'mode': 'abr', 'quality': 3
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'mp3', 'mode': 'cbr', 'quality': 400
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'opus', 'quality': 600
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'wav', 'quality': 13
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'flac', 'quality': 20
        }))
        self.assertFalse(validate_args({
            'main': 'batch', 'output-path': '.',
            'format': 'ogg', 'quality': 20
        }))

    def test_use_memory_gsettings_cbr(self):
        use_memory_gsettings({
            'output-path': '.',
            'main': 'batch',
            'format': 'mp3',
            'mode': 'cbr',
            'quality': '320'
        })
        gio_settings = get_gio_settings()
        self.assertEqual(
            gio_settings.get_string('mp3-mode'), 'cbr'
        )
        self.assertEqual(
            gio_settings.get_string('output-mime-type'),
            'audio/mpeg'
        )
        self.assertEqual(
            gio_settings.get_int('mp3-cbr-quality'),
            320
        )

    def test_use_memory_gsettings_default_mp3_mode(self):
        use_memory_gsettings({
            'output-path': '.',
            'main': 'batch',
            'format': 'mp3',
            'quality': '5'
        })
        gio_settings = get_gio_settings()
        self.assertEqual(
            gio_settings.get_string('mp3-mode'), 'vbr'
        )
        self.assertEqual(
            gio_settings.get_string('output-mime-type'),
            'audio/mpeg'
        )
        self.assertEqual(
            gio_settings.get_int('mp3-vbr-quality'),
            5
        )

    def test_use_memory_gsettings_ogg(self):
        use_memory_gsettings({
            'output-path': '.',
            'main': 'batch',
            'format': 'ogg',
            'quality': '0.5'
        })
        gio_settings = get_gio_settings()
        self.assertEqual(
            gio_settings.get_string('output-mime-type'),
            'audio/x-vorbis'
        )
        self.assertEqual(
            gio_settings.get_double('vorbis-quality'),
            0.5
        )

    def test_set_delete_original_false(self):
        gio_settings = get_gio_settings()
        gio_settings.set_boolean('delete-original', True)
        use_memory_gsettings({
            'output-path': '.',
            'main': 'batch',
            'format': 'ogg',
            'quality': '0.5'
        })
        gio_settings = get_gio_settings()
        self.assertFalse(gio_settings.get_boolean('delete-original'))


if __name__ == "__main__":
    unittest.main()
