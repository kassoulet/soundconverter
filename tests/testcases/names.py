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

"""Test filename handling."""


import unittest
import os
from urllib.parse import unquote
import urllib.parse
import urllib.error
from gi.repository import Gst, Gio

from soundconverter.util.settings import settings, get_gio_settings
from soundconverter.util.namegenerator import TargetNameGenerator, \
    get_subfolder_pattern, get_basename_pattern, process_custom_pattern, \
    custom_patterns
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.fileoperations import filename_to_uri, \
    unquote_filename, beautify_uri
from soundconverter.interface.batch import prepare_files_list

from util import reset_settings


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

    def test_non_recursive_directory(self):
        test = ["tests/test data/empty/"]
        # it should not find anything, as test is a directory
        expectation = ([], [])
        self.assertEqual(prepare_files_list(test), expectation)

    def test_recursive_directory(self):
        settings["recursive"] = True
        test = ["tests/test data/empty/", "tests/test data/empty/b"]
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

    def test_file(self):
        test = ["tests/test data/empty/a"]
        # it should not detect the name of the parent directory as
        # it's only a single file
        expectation = ([filename_to_uri(test[0])], [""])
        result = prepare_files_list(test)
        self.assertTrue(result[0][0].startswith('file://'))
        self.assertEqual(result, expectation)


class Patterns(unittest.TestCase):
    def test_subfolder_pattern(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('subfolder-pattern-index', 1)
        pattern = get_subfolder_pattern()
        self.assertEqual(pattern, '{album-artist}-{album}')

    def test_basename_pattern(self):
        gio_settings = get_gio_settings()

        gio_settings.set_int('name-pattern-index', 2)
        pattern = get_basename_pattern()
        self.assertEqual(pattern, '{track-number:02}-{title}')

        generator = TargetNameGenerator()
        sound_file = SoundFile('file:///foo.bar')
        sound_file.tags.update({
            'track-number': 3,
            'title': 'foo'
        })
        filled = generator.fill_pattern(sound_file, pattern)
        self.assertEqual(filled, '03-foo')

        gio_settings.set_int('name-pattern-index', 5)
        gio_settings.set_string('custom-filename-pattern', 'test')
        pattern = get_basename_pattern()
        self.assertEqual(pattern, 'test')

    def test_process_custom_pattern(self):
        pattern_in = '{Artist}/{Album} foo/{Track}'
        pattern_out = process_custom_pattern(pattern_in)
        self.assertEqual(
            pattern_out, '{artist}/{album} foo/{track-number:02}'
        )

    def test_custom_patterns_mapping(self):
        self.assertEqual(custom_patterns['{Artist}'], '{artist}')


class TargetNameGeneratorTestCases(unittest.TestCase):
    def setUp(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('name-pattern-index', 0)
        gio_settings.set_int('subfolder-pattern-index', 0)
        gio_settings.set_boolean('same-folder-as-input', False)
        gio_settings.set_string('selected-folder', 'file:///test/')
        gio_settings.set_boolean('create-subfolders', True)
        gio_settings.set_boolean('replace-messy-chars', True)
        self.g = TargetNameGenerator()

        self.s = SoundFile("file:///path/to/file.flac")
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

    def test_unquote_filename(self):
        self.assertEqual(unquote_filename('file://baz%20qux'), 'file://baz qux')

    def test_beautify_uri(self):
        self.assertEqual(beautify_uri('file://hostname/'), '/')
        self.assertEqual(beautify_uri('file://hostname/foo'), '/foo')
        self.assertEqual(beautify_uri('file:///baz%20qux'), '/baz qux')
        self.assertEqual(beautify_uri('foo/bar'), 'foo/bar')

    def test_safe_uri(self):
        # the "test data" folder has the space in it on purpose for this spec
        cwd_uri = 'file://' + os.getcwd()

        # 1. path doesn't exist at all
        self.assertEqual(
            self.g.safe_uri('file:///', '/b äz/quズx/foo.mp3'),
            'file:///b_az/qux/foo.mp3'
        )
        self.assertEqual(
            self.g.safe_uri('file:///test/', '/baズz/qux'),
            'file:///test/baz/qux'
        )
        self.assertEqual(
            self.g.safe_uri('file:///', '/ズfoo.mp3'),
            'file:///foo.mp3'
        )
        self.assertEqual(
            self.g.safe_uri('ftp://hostname/', 'ズblä'),
            'ftp://hostname/bla'
        )
        self.assertEqual(
            self.g.safe_uri('ftp://hostname/foo', '/ズ blä'),
            'ftp://hostname/foo/_bla'
        )

        # 2. the outer dir exists
        self.assertEqual(
            self.g.safe_uri(cwd_uri, '/home/qфux/foo.mp3'),
            cwd_uri + '/home/qux/foo.mp3')
        self.assertEqual(
            self.g.safe_uri(cwd_uri, 'tests/asdf/fooф.mp3'),
            cwd_uri + '/tests/asdf/foo.mp3')
        self.assertEqual(
            self.g.safe_uri(cwd_uri, '/tests/asdf/fooф.mp3'),
            cwd_uri + '/tests/asdf/foo.mp3')
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/', 'tests/asdf/fooф.mp3'),
            cwd_uri + '/tests/asdf/foo.mp3')
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests', '/asdf/fooф.mp3'),
            cwd_uri + '/tests/asdf/foo.mp3')
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/', 'asdf/fooф.mp3'),
            cwd_uri + '/tests/asdf/foo.mp3')

        # 3. all dirs exist (space of 'test data' will be kept)
        original_name = os.getcwd() + '/tests/test data/audio/fâoo.mp3'
        self.assertEqual(
            self.g.safe_uri('file:///', original_name),
            cwd_uri + '/tests/test%20data/audio/faoo.mp3'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri, 'tests/test%20data/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri, '/tests/test%20data/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/', 'tests/test%20data/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests', '/test%20data/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/', 'test%20data/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/test%20data', '/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/test data', 'fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/test%20data/', '/fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/test data/', 'fфズ oo.mp3â'),
            cwd_uri + '/tests/test%20data/f_oo.mp3a'
        )

        # 4. the complete path exists
        original_name = os.getcwd() + '/tests/test%20data/audio/a.wav'
        self.assertEqual(
            self.g.safe_uri('file:///', original_name),
            cwd_uri + '/tests/test%20data/audio/a.wav'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri, '/tests/test data/'),
            cwd_uri + '/tests/test%20data/'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri, 'tests/test data/'),
            cwd_uri + '/tests/test%20data/'
        )

        # 5. paths with special chars can be transformed into existing paths.
        # Doesn't increment the filename. on_task_finished of gstreamer.py
        # does that later. To reuse paths that were generated from {artist}
        # tags with special characters
        original_name = os.getcwd() + '/tests/test%20data/âuズdio/â.wav'
        self.assertEqual(
            self.g.safe_uri('file:///', original_name),
            cwd_uri + '/tests/test%20data/audio/a.wav'
        )

        # 6. doesn't change %20 spaces in URIs into _20, but rather into _
        # and keeps the URI scheme.
        # test%20data exists (test data), so it keeps the %20, because the
        # output should be an uri as well, just like the input.
        original_name = os.getcwd() + '/tests/test%20data/fo%20o.mp3'
        self.assertEqual(
            self.g.safe_uri('file:///', original_name),
            cwd_uri + '/tests/test%20data/fo_o.mp3'
        )

        # 7. any path added as parent is not modified
        self.assertEqual(
            self.g.safe_uri('file:///ab cd', 'fo o.mp3'),
            'file:///ab%20cd/fo_o.mp3'
        )
        self.assertEqual(
            self.g.safe_uri('file:///fфズ', 'fo o.mp3'),
            'file:///f%D1%84%E3%82%BA/fo_o.mp3'
        )
        self.assertEqual(
            self.g.safe_uri(cwd_uri + '/tests/test data', 'audio/a.wav'),
            cwd_uri + '/tests/test%20data/audio/a.wav'
        )

        # 8. some weird URI schema means that 'test data' is probably not our
        # existing folder in the filesystem. The URI scheme should be file://
        # for that. Hence replace the space.
        original_name = 'tests/test%20data/fo%20o.mp3'
        self.assertEqual(
            self.g.safe_uri('foo://' + os.getcwd(), original_name),
            'foo://' + os.getcwd() + '/tests/test_data/fo_o.mp3'
        )
        # don't break uri authorities
        original_name = 'tests/test%20data/fo%20o.mp3'
        self.assertEqual(
            self.g.safe_uri('foo://foo@bar:1234/', original_name),
            'foo://foo@bar:1234/tests/test_data/fo_o.mp3'
        )

    def test_suffix(self):
        get_gio_settings().set_string('output-mime-type', 'audio/x-vorbis')
        # figures out the suffix when created
        self.g = TargetNameGenerator()
        self.g.same_folder_as_input = True
        self.g.create_subfolders = False
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/path/to/file.ogg"
        )

    def test_no_extension(self):
        get_gio_settings().set_string('output-mime-type', 'audio/x-m4a')
        # figures out the suffix when created
        self.g = TargetNameGenerator()
        self.s = SoundFile("file:///path/to/file")
        self.g.same_folder_as_input = True
        self.g.create_subfolders = False
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/path/to/file.m4a"
        )

    def test_basename(self):
        self.g.suffix = "ogg"
        self.g.basename_pattern = "{track-number:02}-{title}"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/path/to/01-Hi_Ho.ogg"
        )

    def test_location(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music"
        self.g.subfolder_pattern = "{artist}/{album}"
        self.g.basename_pattern = "{track-number:02}-{title}"
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg"
        )

    def test_location_escape(self):
        self.s = SoundFile("file:///path/to/file with spaces")
        self.g.replace_messy_chars = False
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///mu sic"
        self.g.create_subfolders = False
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "file:///mu%20sic/file%20with%20spaces.ogg"
        )

    def test_basename_with_spaces(self):
        uri = 'file:///spa%20ce/sub%20folder/foo.mp3'
        self.s = SoundFile(uri, 'file:///spa%20ce/')
        self.g.replace_messy_chars = False
        self.g.suffix = "ogg"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "file:///spa%20ce/sub%20folder/foo.ogg"
        )

    def test_basename_with_spaces_messy(self):
        uri = 'file:///spa%20ce/sub%20folder/foo.mp3'
        self.s = SoundFile(uri, 'file:///spa%20ce/')
        self.g.replace_messy_chars = True
        self.g.suffix = "ogg"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "file:///spa%20ce/sub_folder/foo.ogg"
        )

    def test_basename_with_spaces_existing(self):
        base_path = 'file:///' + os.getcwd() + '/tests/test%20data'
        uri = base_path + '/audio/a.wav'
        self.s = SoundFile(uri, base_path)
        self.g.replace_messy_chars = False
        self.g.suffix = "ogg"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            base_path + '/audio/a.ogg'
        )

    def test_basename_with_spaces_existing_messy(self):
        base_path = 'file:///' + os.getcwd() + '/tests/test%20data'
        uri = base_path + '/audio/a.wav'
        self.s = SoundFile(uri, base_path)
        self.g.replace_messy_chars = True
        self.g.suffix = "ogg"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            base_path + '/audio/a.ogg'
        )

    def test_uri(self):
        self.g.suffix = "ogg"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh://user@server:port/path/to/%20file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "ssh://user@server:port/path/to/%20file.ogg"
        )

    def testURILocalDestination(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music"
        self.g.create_subfolders = False

        self.s = SoundFile("ssh://user@server:port/p%25ath/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "file:///music/file.ogg"
        )

    def test_uri_distant_destination(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = "ftp://user2@dest-server:another-port:/music/"
        self.g.create_subfolders = False

        self.s = SoundFile("ssh://user@server:port/path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "ftp://user2@dest-server:another-port:/music/file.ogg"
        )

    def testUriLikePaths(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music%20"
        self.g.same_folder_as_input = False
        self.s = SoundFile("file:///path/%2525")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.subfolder_pattern = "{artist}/{album}"
        self.g.create_subfolders = True
        self.g.replace_messy_chars = False
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/music /Foo Bar/IS: TOO/%25.ogg"
        )

    def test_uri_like_paths_messy(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music%20"
        self.g.same_folder_as_input = False
        self.s = SoundFile("file:///path/%2525")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.subfolder_pattern = "{artist}/{album}"
        self.g.create_subfolders = True
        self.g.replace_messy_chars = True
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/music /Foo_Bar/IS__TOO/_25.ogg"
        )

    def test_uri_unicode(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = (
                "ftp://user2@dest-server:another-port:" + quote("/mûsîc/")
        )
        self.g.replace_messy_chars = False
        self.g.create_subfolders = False

        self.s = SoundFile(
            "ssh://user@server:port" + quote(
                "/path/to/file with \u041d chars.flac"
            )
        )
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "ftp://user2@dest-server:another-port:/m%C3%BBs%C3%AEc/file"
            "%20with%20%D0%9D%20chars.ogg"
        )

    def testURIUnicode_utf8(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = (
                "ftp://user2@dest-server:another-port:" + quote("/mûsîc/")
        )
        self.g.replace_messy_chars = False

        self.s = SoundFile(
            "ssh://user@server:port" + quote(
                "/path/to/file with strângë chàrs фズ.flac"
            )
        )
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.create_subfolders = False
        self.g.same_folder_as_input = False
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "ftp://user2@dest-server:another-port:" +
            quote("/mûsîc/file with strângë chàrs фズ.ogg")
        )

    def test_uri_unicode_messy(self):
        self.g.suffix = "ogg"
        self.g.selected_folder = (
                "ftp://user2@dest-server:another-port:" + quote("/mûsîc/")
        )

        self.s = SoundFile(
            "ssh://user@server:port" +
            quote("/path/to/file with strângë chàrs.flac")
        )
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.replace_messy_chars = True
        self.g.create_subfolders = False
        self.g.same_folder_as_input = False
        self.assertEqual(
            self.g.generate_target_uri(self.s),
            "ftp://user2@dest-server:another-port:/" +
            quote("mûsîc") + "/file_with_strange_chars.ogg"
        )

    def testDisplay(self):
        self.g.suffix = "ogg"

        self.s = SoundFile("ssh://user@server:port/path/to/file.flac")
        self.assertEqual(
            self.s.filename_for_display,
            "file.flac"
        )
        self.s = SoundFile("ssh://user@server:port/path/to/fîlé.flac")
        self.assertEqual(
            self.s.filename_for_display,
            "fîlé.flac"
        )
        self.s = SoundFile(
            "ssh://user@server:port/path/to/fileфズ.flac"
        )
        self.assertEqual(self.s.filename_for_display, "fileфズ.flac")

    def test8bits(self):
        self.s = SoundFile(
                'file://' + quote("/path/to/file\xa0\xb0\xc0\xd0.flac")
        )
        self.g.suffix = "ogg"
        self.g.replace_messy_chars = False
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s, False),
            'file://' + quote("/path/to/file\xa0\xb0\xc0\xd0.ogg")
        )

    def test8bits_messy(self):
        self.s = SoundFile(
            'file://' + quote("/path/to/file\xa0\xb0\xc0\xd0.flac")
        )
        self.g.suffix = "ogg"
        self.g.replace_messy_chars = True
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s, False),
            "file:///path/to/file_A.ogg"
        )

    def test8bits_tags(self):
        self.g.replace_messy_chars = False
        self.s = SoundFile("file:///path/to/fileyop.flac")
        self.s.tags.update({
            "artist": "\xa0\xb0\xc0\xd0",
            "title": "\xa1\xb1\xc1\xd1",
            "album": "\xa2\xb2\xc2\xd2",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music"
        self.g.subfolder_pattern = "{artist}/{album}"
        self.g.basename_pattern = "{title}"
        self.assertEqual(
            self.g.generate_target_uri(self.s, False),
            'file://' + quote(
                "/music/\xa0\xb0\xc0\xd0/\xa2\xb2"
                "\xc2\xd2/\xa1\xb1\xc1\xd1.ogg"
            )
        )

    def test_root(self):
        self.s = SoundFile("file:///path/to/file.flac", "file:///path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = "ogg"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/path/to/file.ogg"
        )

    def test_root_path(self):
        self.s = SoundFile("file:///path/#to/file.flac", "file:///path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music"

        self.g.replace_messy_chars = False
        self.g.create_subfolders = False
        self.g.same_folder_as_input = False

        self.assertEqual(
            self.g.generate_target_uri(self.s, False),
            "file:///music/%23to/file.ogg"
        )

    def test_root_custom_pattern(self):
        self.s = SoundFile("file:///path/#to/file.flac", "file:///path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11
        })
        self.g.suffix = "ogg"
        self.g.basename_pattern = "{genre}/{title}"

        self.g.replace_messy_chars = True
        self.g.create_subfolders = False
        self.g.same_folder_as_input = True

        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            # basefolder handling is disabled when the pattern has a /
            "/path/Unknown_Genre/Hi_Ho.ogg"
        )

    def test_default_pattern_values(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('name-pattern-index', -1)
        # without timestamp because I'd like to avoid having a test that
        # fails randomly
        gio_settings.set_string('custom-filename-pattern', (
            '{Artist}/{Album}/{Album-Artist}/{Title}/{Track}/{Total}/{Genre}'
            '/{Date}/{Year}/{DiscNumber}/{DiscTotal}/{Ext}/{inputname}/'
            '{filename}'
        ))
        self.g = TargetNameGenerator()

        self.s = SoundFile("file:///file.flac", "file:///")
        self.g.suffix = "ogg"
        self.g.replace_messy_chars = False
        self.g.create_subfolders = False
        self.g.selected_folder = 'file:///foo'
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/foo/Unknown Artist/Unknown Album/Unknown Artist/file/00/00/"
            "Unknown Genre/Unknown Date/Unknown Year/0/0/ogg/file/file.ogg"
        )

    def test_find_format_string_tags(self):
        pattern = '{i}{a}b{c}{{d}}{e}c{{{g}}}{hhh}'
        variables = self.g.find_format_string_tags(pattern)
        mapping = {variable: 1 for variable in variables}
        formatted = pattern.format(**mapping)
        # if it didn't crash it's already working actually
        self.assertEqual(formatted, '11b1{d}1c{1}1')

    def test_pattern_unknown_tag(self):
        gio_settings = get_gio_settings()
        gio_settings.set_int('name-pattern-index', -1)
        # without timestamp because I'd like to avoid having a test that
        # fails randomly
        gio_settings.set_string('custom-filename-pattern', (
            '{venue}/{weather}'
        ))
        self.g = TargetNameGenerator()

        self.s = SoundFile("file:///file.flac", "file:///")
        self.g.suffix = "ogg"
        self.g.replace_messy_chars = False
        self.g.create_subfolders = False
        self.g.selected_folder = 'file:///foo'
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/foo/Unknown Venue/Unknown Weather.ogg"
        )

    def test_leading_slash_pattern(self):
        self.s = SoundFile("file:///path/#to/file.flac", "file:///path/")
        self.s.tags.update({
            "title": "Hi Ho"
        })
        self.g.suffix = "ogg"
        # basename_patterns can be user defined in a text input. if it
        # contains slashes, the subfolder_pattern will be overwritten,
        # so that custom subfolder patterns can be used by typing into
        # the basename pattern.
        self.g.basename_pattern = "/home/foo/{title}"
        self.g.create_subfolders = True
        self.g.subfolder_pattern = "/bar"
        self.g.selected_folder = "/asdf"
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/asdf/home/foo/Hi_Ho.ogg"
        )

    def test_leading_slash_subfolder_pattern(self):
        self.s = SoundFile("file:///path/#to/file.flac", "file:///path/")
        self.s.tags.update({
            "title": "Hi Ho"
        })
        self.g.suffix = "ogg"
        self.g.basename_pattern = "{title}"
        self.g.create_subfolders = True
        self.g.subfolder_pattern = "/bar"
        self.g.selected_folder = "/asdf"
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/asdf/bar/Hi_Ho.ogg"
        )

    def test_root_path_custom_pattern(self):
        self.s = SoundFile("file:///path/to/file.flac", "file:///path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = "ogg"
        self.g.selected_folder = "file:///music"
        self.g.basename_pattern = "{title}"
        self.g.create_subfolders = False
        self.g.same_folder_as_input = False
        self.assertEqual(
            self.g.generate_target_uri(self.s, True),
            "/music/to/Hi_Ho.ogg"
        )

    def test_quote(self):
        self.s = SoundFile('file://' + quote("/path%'#/to/file%'#.flac"))
        self.s.tags.update({
            "artist": "Foo%'#Bar",
            "title": "Hi%'#Ho",
        })
        self.g.replace_messy_chars = False
        self.g.same_folder_as_input = True
        self.g.create_subfolders = False
        self.g.suffix = "ogg"
        self.assertEqual(
            self.g.generate_target_uri(self.s, False),
            'file://' + quote("/path%'#/to/file%'#.ogg")
        )
        self.g.create_subfolders = True
        self.g.subfolder_pattern = "{artist}"
        self.g.basename_pattern = "{title}"
        self.assertEqual(
            self.g.generate_target_uri(self.s, False),
            'file://' + quote("/path%'#/to/Foo%'#Bar/Hi%'#Ho.ogg")
        )

    # temporary filename generation

    def test_temporary1(self):
        self.s = SoundFile('file:///foo/bar.mp3')
        self.g.same_folder_as_input = False
        self.g.replace_messy_chars = True
        self.g.selected_folder = 'file:///music'
        temp_path = self.g.generate_temp_path(self.s)
        expected = 'file:///music/bar.mp3_'
        self.assertTrue(
            temp_path.startswith(expected),
            'expected {} to start with {}'.format(temp_path, expected)
        )
        self.assertTrue(temp_path.endswith('_SC_'))

    def test_temporary2(self):
        self.s = SoundFile('file:///foo/bar.mp3', 'file:///')
        # base_path 'file:///' will be ignored
        self.g.same_folder_as_input = False
        self.g.replace_messy_chars = False
        self.g.selected_folder = 'file:///music'
        temp_path = self.g.generate_temp_path(self.s)
        expected = 'file:///music/bar.mp3~'
        self.assertTrue(
            temp_path.startswith(expected),
            'expected {} to start with {}'.format(temp_path, expected)
        )
        self.assertTrue(temp_path.endswith('~SC~'))

    def test_temporary3(self):
        self.s = SoundFile('file:///foo/bar.mp3')
        self.g.same_folder_as_input = True
        self.g.replace_messy_chars = True
        self.g.selected_folder = 'file:///etfdzhdrudf'
        temp_path = self.g.generate_temp_path(self.s)
        expected = 'file:///foo/bar.mp3_'
        self.assertTrue(
            temp_path.startswith(expected),
            'expected {} to start with {}'.format(temp_path, expected)
        )
        self.assertTrue(temp_path.endswith('_SC_'))

    def test_temporary4(self):
        self.s = SoundFile('file:///foo/bar.mp3')
        self.g.same_folder_as_input = True
        self.g.replace_messy_chars = False
        self.g.selected_folder = 'file:///etfdzhdrudf'
        temp_path = self.g.generate_temp_path(self.s)
        expected = 'file:///foo/bar.mp3~'
        self.assertTrue(
            temp_path.startswith(expected),
            'expected {} to start with {}'.format(temp_path, expected)
        )
        self.assertTrue(temp_path.endswith('~SC~'))

    def test_temporary5(self):
        self.s = SoundFile('file:///foo/test/bar.mp3', 'file:///foo/')
        self.g.same_folder_as_input = True
        self.g.replace_messy_chars = False
        self.g.selected_folder = 'file:///etfdzhdrudf'
        temp_path = self.g.generate_temp_path(self.s)
        expected = 'file:///foo/bar.mp3~'
        self.assertTrue(
            temp_path.startswith(expected),
            'expected {} to start with {}'.format(temp_path, expected)
        )
        self.assertTrue(temp_path.endswith('~SC~'))


if __name__ == "__main__":
    unittest.main()
