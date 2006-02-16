import unittest
from soundconverter import *

class TargetNameGeneratorTestCases(unittest.TestCase):

    def setUp(self):
        self.g = TargetNameGenerator()
        self.g.set_exists(self.never_exists)
        self.g.set_replace_messy_chars(True)

        self.s = SoundFile("file:///path/to/file.flac")
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
                             "file:///path/to/file.ogg")

    def testBasename(self):
        self.g.set_target_suffix(".ogg")
        self.g.set_basename_pattern("%(track-number)02d-%(title)s")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "file:///path/to/01-Hi_Ho.ogg")

    def testLocation(self):
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("/music")
        self.g.set_subfolder_pattern("%(artist)s/%(album)s")
        self.g.set_basename_pattern("%(track-number)02d-%(title)s")
        self.failUnlessEqual(self.g.get_target_name(self.s),
                             "file:///music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg")

    def testTargetExists(self):
        self.g.set_exists(self.always_exists)
        self.g.set_target_suffix(".ogg")
        self.g.set_folder("/")
        self.failUnlessRaises(TargetNameCreationFailure,
                              self.g.get_target_name,
                              self.s)


if __name__ == "__main__":
    unittest.main()
