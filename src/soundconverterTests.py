# -*- coding: utf-8 -*-

import unittest
from urllib import quote, unquote
from soundconverter import *

class TargetNameGeneratorTestCases(unittest.TestCase):

    def setUp(self):
        self.g = TargetNameGenerator()
        self.g.set_exists(self.never_exists)
        self.g.set_replace_messy_chars(True)

        self.s = SoundFile("/path/to/file.flac")
        self.s.add_tags({
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
        self.g.set_target_suffix(".ogg")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/file.ogg")

    def testBasename(self):
        self.g.set_target_suffix(".ogg")
        self.g.set_basename_pattern("%(track-number)02d-%(title)s")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/path/to/01-Hi_Ho.ogg")

    def testLocation(self):
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("/music")
        self.g.set_subfolder_pattern("%(artist)s/%(album)s")
        self.g.set_basename_pattern("%(track-number)02d-%(title)s")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg")


    def testURI(self):
        self.g.set_exists(self.always_exists)
        self.g.set_target_suffix(".ogg")
        #self.g.set_folder("/")
        
        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.add_tags({
            "artist": "Foo Bar", 
            "title": "Hi Ho", 
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ssh:user@server:port///path/to/file.ogg")

    def testURILocalDestination(self):
        self.g.set_exists(self.always_exists)
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("/music")
        
        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.add_tags({
            "artist": "Foo Bar", 
            "title": "Hi Ho", 
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "/music/file.ogg")

    def testURIDistantDestination(self):
        self.g.set_exists(self.always_exists)
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("ftp:user2@dest-server:another-port:/music/")
        
        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.add_tags({
            "artist": "Foo Bar", 
            "title": "Hi Ho", 
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/music/file.ogg")
                            
    def testURIUnicode(self):
        self.g.set_exists(self.always_exists)
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("ftp:user2@dest-server:another-port:" + quote("/mûsîc/"))
        self.g.set_replace_messy_chars(False)
        
        self.s = SoundFile("ssh:user@server:port" + quote("///path/to/file with strângë chàrs.flac"))
        self.s.add_tags({
            "artist": "Foo Bar", 
            "title": "Hi Ho", 
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:" + quote("/mûsîc/file with strângë chàrs.ogg"))

    def testURIUnicodeMessy(self):
        self.g.set_exists(self.always_exists)
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("ftp:user2@dest-server:another-port:" + quote("/mûsîc/"))
        
        self.s = SoundFile("ssh:user@server:port" + quote("///path/to/file with strângë chàrs.flac"))
        self.s.add_tags({
            "artist": "Foo Bar", 
            "title": "Hi Ho", 
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "ftp:user2@dest-server:another-port:/" + quote("mûsîc") + "/file_with_strange_chars.ogg")
                              

                              
if __name__ == "__main__":
    unittest.main()
