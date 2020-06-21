#!/usr/bin/python3
# -*- coding: utf-8 -*-

import unittest
from soundconverter.formats import get_mime_type


class Format(unittest.TestCase):
    def test_get_mime_type(self):
        self.assertEqual(get_mime_type('mp3'), 'audio/mpeg')
        self.assertEqual(get_mime_type('audio/x-m4a'), 'audio/x-m4a')


if __name__ == "__main__":
    unittest.main()
