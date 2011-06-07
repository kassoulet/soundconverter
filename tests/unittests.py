# -*- coding: utf-8 -*-

import unittest
from urllib import unquote
import urllib
from soundconverter import *

from soundconverter.namegenerator import TargetNameGenerator
from soundconverter.soundfile import SoundFile
from soundconverter.fileoperations import filename_to_uri

def quote(ss):
	if isinstance(ss, unicode):
		ss = ss.encode('utf-8')
	return urllib.quote(ss)

class FilenameToUriTest(unittest.TestCase):

    def test(self):
        for i in (
            'foo',
            '/foo',
            'foo/bar',
            '/foo/bar',
            'http://example.com/foo'
        ):
            got = filename_to_uri(i)
            self.failUnless('://' in got)



class TargetNameGeneratorTestCases(unittest.TestCase):

    def setUp(self):
        self.g = TargetNameGenerator()
        self.g.exists = self.never_exists
        self.g.replace_messy_chars = True

        self.s = SoundFile("/path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })

    def tearDown(self):
        self.g = None
        self.s = None

    def never_exists(self, pathname):
        return False

    def always_exists(self, pathname):
        return True

    def testSuffix(self):
        self.g.suffix = ".ogg"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")

    def testNoSuffix(self):
    	try:
    		self.g.get_target_name(self.s)
    	except AssertionError:
    		return # ok
    	assert False

    def testNoExtension(self):
        self.g.suffix = ".ogg"
        self.s = SoundFile("/path/to/file")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")
    def testBasename(self):
        self.g.suffix = ".ogg"
        self.g.basename = "%(track-number)02d-%(title)s"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/01-Hi_Ho.ogg")

    def testLocation(self):
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.subfolders = "%(artist)s/%(album)s"
        self.g.basename = "%(track-number)02d-%(title)s"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg")

    def testLocationEscape(self):
        self.s = SoundFile("/path/to/file with spaces")
        self.g.replace_messy_chars = False
        self.g.suffix = ".ogg"
        self.g.folder = "/mu sic"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/mu%20sic/file%20with%20spaces.ogg")

    def testURI(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        #self.g.folder = "/")

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ssh:user@server:port///path/to/file.ogg")

    def testURILocalDestination(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "/music"

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/music/file.ogg")

    def testURIDistantDestination(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:/music/"

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/music/file.ogg")

    def testURIUnicode(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh:user@server:port" + quote(u"///path/to/file with \u041d chars.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/m%C3%BBs%C3%AEc/file%20with%20%D0%9D%20chars.ogg")

    def testURIUnicode_utf8(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh:user@server:port" + quote("///path/to/file with strângë chàrs фズ.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:" + quote("/mûsîc/file with strângë chàrs фズ.ogg"))

    def testURIUnicodeMessy(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")

        self.s = SoundFile("ssh:user@server:port" + quote("///path/to/file with strângë chàrs.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/" + quote("mûsîc") + "/file_with_strange_chars.ogg")

    def testDisplay(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        #self.g.folder = "/")

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.failUnlessEqual(self.s.filename_for_display,
                             "file.flac")
        self.s = SoundFile("ssh:user@server:port///path/to/fîlé.flac")
        self.failUnlessEqual(self.s.filename_for_display,
                             "fîlé.flac")
        self.s = SoundFile("ssh:user@server:port///path/to/\xaa.flac")
        self.failUnlessEqual(self.s.filename_for_display,
                             u"\ufffd.flac")

    def test8bits(self):
        self.s = SoundFile(quote("/path/to/file\xa0\xb0\xc0\xd0.flac"))
        self.g.suffix = ".ogg"
        self.g.replace_messy_chars = False
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             quote("/path/to/file\xa0\xb0\xc0\xd0.ogg"))

    def test8bits_messy(self):
        self.s = SoundFile(quote("/path/to/file\xa0\xb0\xc0\xd0.flac"))
        self.g.suffix = ".ogg"
        self.g.replace_messy_chars = True
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/file__A__.ogg")


    def test8bits_tags(self):
        self.g.replace_messy_chars = False
        self.s = SoundFile("/path/to/fileyop.flac")
        self.s.tags.update({
            "artist": "\xa0\xb0\xc0\xd0",
            "title": "\xa1\xb1\xc1\xd1",
            "album": "\xa2\xb2\xc2\xd2",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.subfolders = "%(artist)s/%(album)s"
        self.g.basename = "%(title)s"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             quote("/music/\xa0\xb0\xc0\xd0/\xa2\xb2\xc2\xd2/\xa1\xb1\xc1\xd1.ogg"))
                             
                             
    def testRoot(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.g.suffix = ".ogg"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")


    def testRootPath(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        #self.g.basename = "%(title)s")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/music/to/file.ogg")

    def testRootCustomPattern(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.g.suffix = ".ogg"
        self.g.basename = "%(title)s"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/Hi_Ho.ogg")

    def testRootPathCustomPattern(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.basename = "%(title)s"
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/music/to/Hi_Ho.ogg")

if __name__ == "__main__":
    unittest.main()
