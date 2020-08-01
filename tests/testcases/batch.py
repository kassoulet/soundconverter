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


class BatchUtils(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_prepare_files_list(self):
        settings['recursive'] = True
        parsed_files, subdirectories = prepare_files_list(['tests/test data/audio/b/'])
        self.assertListEqual(
            parsed_files,
            ['file://' + os.path.realpath('tests/test%20data/audio/b/c.mp3')]
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


if __name__ == "__main__":
    unittest.main()
