#!/usr/bin/python3
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2025 Gautier Portet
# Copyright 2020-2025 Sezanzeb
#
# Regression test for bug 2165300: NTFS drive hang on scanning
#   file:///mnt/DATA/Music/Unsorted/Lost%20%282005%29
# Root cause was encoding mismatch between urllib (%28) and Gio (plain '(')
# and case-insensitivity of NTFS.

import os
import shutil
import tempfile
import unittest
import urllib.parse

from gi.repository import Gio

from soundconverter.util.fileoperations import filename_to_uri, vfs_walk
from soundconverter.util.soundfile import SoundFile


class NTFSErrorTest(unittest.TestCase):
    """Regression for NTFS hang: ValueError uri needs to start with base_path."""

    def test_filename_to_uri_uses_gio_encoding_for_parens(self):
        # Gio leaves '(' unescaped, urllib quotes as %28. filename_to_uri must
        # match Gio to be consistent with vfs_walk.
        # Bug report path: Lost (2005) -> Lost%20%282005%29 vs Lost%20(2005)
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "Lost (2005)")
            os.makedirs(path)
            uri = filename_to_uri(path)
            # should be Gio style: %20 for space, plain parens
            self.assertIn("Lost%20(2005)", uri)
            self.assertNotIn("%28", uri)
            self.assertNotIn("%29", uri)

            # when input is already an uri with encoded parens, it should be
            # normalized to Gio style
            encoded = "file:///tmp/test%20%282005%29"
            self.assertEqual(filename_to_uri(encoded), "file:///tmp/test%20(2005)")

            plain = "file:///tmp/test%20(2005)"
            self.assertEqual(filename_to_uri(plain), "file:///tmp/test%20(2005)")
        finally:
            shutil.rmtree(tmp)

    def test_soundfile_tolerant_to_parens_encoding(self):
        # base with urllib encoding (%28) and file with Gio encoding (plain)
        # must not raise. This is the exact mismatch from the bug report.
        base_urllib = "file:///tmp/test%20%282005%29/"
        file_gio = "file:///tmp/test%20(2005)/a.mp3"
        # should not raise
        sf = SoundFile(file_gio, base_urllib)
        self.assertEqual(sf.filename, "a.mp3")
        # canonical base loses %28 -> Gio plain, trailing slash preserved
        self.assertEqual(sf.base_path, "file:///tmp/test%20(2005)/")
        self.assertEqual(sf.uri, file_gio)

        # also reverse: base Gio plain, file urllib encoded should also be tolerant
        # (via unquote fallback)
        sf2 = SoundFile(
            "file:///tmp/test%20%282005%29/a.mp3", "file:///tmp/test%20(2005)/"
        )
        self.assertEqual(sf2.filename, "a.mp3")

    def test_soundfile_tolerant_to_ntfs_case_insensitivity(self):
        # NTFS is case-insensitive: /mnt/DATA vs /mnt/data should not raise
        # Simulate walking returns canonical upper case while base is lower case
        base_lower = "file:///mnt/data/Music/"
        file_upper = "file:///mnt/DATA/Music/song.mp3"
        sf = SoundFile(file_upper, base_lower)
        self.assertEqual(sf.filename, "song.mp3")
        # also test with subfolders
        file_upper2 = "file:///mnt/DATA/Music/Unsorted/song.mp3"
        sf2 = SoundFile(file_upper2, base_lower)
        self.assertEqual(sf2.filename, "song.mp3")
        self.assertIn("Unsorted", sf2.subfolders)

    def test_soundfile_vfs_walk_parens_integration(self):
        # End-to-end: create temp dir with parens, walk it, create SoundFiles
        # with parent base (as FileList does for single directory case)
        tmp = tempfile.mkdtemp()
        try:
            # simulate /mnt/DATA/Music/Unsorted/Lost (2005)
            base_dir = os.path.join(tmp, "Unsorted")
            os.makedirs(base_dir)
            lost = os.path.join(base_dir, "Lost (2005)")
            os.makedirs(lost)
            for name in ["song (remix).mp3", "track.mp3"]:
                open(os.path.join(lost, name), "w").close()

            # input uri as user would pass via terminal (filename_to_uri)
            # old urllib style would be %28, new Gio style is plain
            uri_old_style = "file://" + urllib.parse.quote(lost)  # %28
            # filelist walks with Gio, returns Gio style
            files = vfs_walk(uri_old_style)
            self.assertEqual(len(files), 2)
            for f in files:
                self.assertIn("Lost%20(2005)", f)
                self.assertNotIn("%28", f)

            # base as FileList does: parent of input uri
            # FileList now uses Gio.get_parent().get_uri()
            parent_gio = Gio.file_parse_name(uri_old_style).get_parent().get_uri()
            base = parent_gio + "/"
            # base should be .../Unsorted/ (parent, not Lost)
            self.assertTrue(base.endswith("Unsorted/"))

            # This must not raise (previously hung with ValueError)
            for f in files:
                sf = SoundFile(f, base)
                self.assertIsNotNone(sf.filename)
                # subfolders should contain Lost (2005)
                self.assertIn("Lost (2005)", sf.subfolders)

            # also test commonprefix case: files inside same folder, base includes folder
            # (e.g. when adding multiple files, not a directory)
            # Simulate commonprefix base that includes the folder with encoded parens
            files_common = files
            # base via commonprefix would be file:///tmp/.../Lost%20(2005)/
            # if we used old urllib base, it would be %28, but files are plain
            base_common_urllib = os.path.commonprefix(
                [uri_old_style + "/a.mp3", uri_old_style + "/b.mp3"]
            )
            # commonprefix gives encoded %28 version
            self.assertIn("%28", base_common_urllib)
            if not base_common_urllib.endswith("/"):
                base_common_urllib += "/"
            # ensure tolerant SoundFile still works when base is encoded but file is plain
            for f in files_common:
                sf = SoundFile(f, base_common_urllib)
                # SoundFile stores filename still quoted (%20)
                self.assertEqual(sf.filename, os.path.basename(f))

        finally:
            shutil.rmtree(tmp)

    def test_soundfile_still_raises_for_unrelated_base(self):
        # Ensure we didn't make it too permissive: unrelated base must still raise
        with self.assertRaises(ValueError):
            SoundFile("file:///tmp/a/b.mp3", "file:///tmp/c/")
        with self.assertRaises(ValueError):
            SoundFile("file:///mnt/DATA/Music/song.mp3", "file:///tmp/other/")


if __name__ == "__main__":
    unittest.main()
