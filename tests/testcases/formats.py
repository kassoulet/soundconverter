#!/usr/bin/python3
# -*- coding: utf-8 -*-

import unittest
from soundconverter.formats import get_mime_type, get_quality


class Format(unittest.TestCase):
    def test_get_mime_type(self):
        self.assertEqual(get_mime_type('mp3'), 'audio/mpeg')
        self.assertEqual(get_mime_type('audio/x-m4a'), 'audio/x-m4a')

    def test_get_quality(self):
        self.assertEqual(get_quality('mp3', 0, 'cbr'), 64)
        self.assertEqual(get_quality('aac', 1, 'thetgdfgsfd'), 96)
        self.assertEqual(get_quality('aac', 256, reverse=True), 4)
        self.assertEqual(get_quality('mp3', 320, mode='abr', reverse=True), 5)


if __name__ == "__main__":
    unittest.main()
