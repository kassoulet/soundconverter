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
from soundconverter.util.fileoperations import split_uri, is_uri


class Fileoperations(unittest.TestCase):
    def test_split_uri_1(self):
        scheme, path = split_uri('file:///one/two/three')
        self.assertEqual(scheme, 'file://')
        self.assertEqual(path, '/one/two/three')

    def test_split_uri_2(self):
        scheme, path = split_uri('file:///three')
        self.assertEqual(scheme, 'file://')
        self.assertEqual(path, '/three')

    def test_split_uri_3(self):
        scheme, path = split_uri('ftp://foo@bar:1234:/one/two/three')
        self.assertEqual(scheme, 'ftp://foo@bar:1234:')
        self.assertEqual(path, '/one/two/three')

    def test_split_uri_4(self):
        scheme, path = split_uri('file:///')
        self.assertEqual(scheme, 'file://')
        self.assertEqual(path, '/')

    def test_wrong_type(self):
        error = None
        try:
            scheme, path = split_uri([1, 2, 3])
        except Exception as e:
            error = e
        self.assertIsNotNone(error)

    def test_is_uri(self):
        self.assertTrue(is_uri('file:///one/two/three'))
        self.assertTrue(is_uri('file:///three'))
        self.assertTrue(is_uri('ftp://foo@bar:1234:/one/two/three'))

        self.assertFalse(is_uri('/folder/file'))
        self.assertFalse(is_uri('./folder/file'))
        self.assertFalse(is_uri('folder/file'))

        self.assertFalse(is_uri('file///one/two/three'))
        self.assertFalse(is_uri('file:/three'))
        self.assertFalse(is_uri('://foo@bar:1234:/one/two/three'))
        self.assertFalse(is_uri('file://'))


if __name__ == "__main__":
    unittest.main()
