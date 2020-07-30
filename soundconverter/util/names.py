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

"""Utils for generating names."""

import string
import time
import re
import os
from random import random
import urllib.request
import urllib.parse
import urllib.error
import unicodedata
from gettext import gettext as _
from soundconverter.util.fileoperations import vfs_exists, filename_to_uri, \
    unquote_filename, split_URI
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.formats import get_file_extension
from soundconverter.audio.profiles import audio_profiles_dict

basename_patterns = [
    ('%(.inputname)s', _('Same as input, but replacing the suffix')),
    ('%(.inputname)s%(.ext)s', _('Same as input, but with an additional suffix')),
    ('%(track-number)02d-%(title)s', _('Track number - title')),
    ('%(title)s', _('Track title')),
    ('%(artist)s-%(title)s', _('Artist - title')),
    ('Custom', _('Custom filename pattern')),
]

subfolder_patterns = [
    ('%(album-artist)s/%(album)s', _('artist/album')),
    ('%(album-artist)s-%(album)s', _('artist-album')),
    ('%(album-artist)s - %(album)s', _('artist - album')),
]


def get_basename_pattern():
    """Get the currently selected or custom filename pattern.

    For example '%(artist)s-%(title)s', without target extension.

    A custom-filename-pattern can also serve the purpose of a subfolder-pattern
    by having forward slashes.
    """
    settings = get_gio_settings()
    index = settings.get_int('name-pattern-index')
    if index >= len(basename_patterns):
        index = 0
    if index == len(basename_patterns) - 1:
        return settings.get_string('custom-filename-pattern')
    else:
        # an index of -1 selects the last entry on purpose
        return basename_patterns[index][0]


def get_subfolder_pattern():
    """Get the currently selected subfolder pattern.

    For example '%(album-artist)s/%(album)s', to create those new
    subfolders in the slected_folder based on tags.
    """
    settings = get_gio_settings()
    index = settings.get_int('subfolder-pattern-index')
    if index >= len(subfolder_patterns):
        index = 0
    return subfolder_patterns[index][0]


class TargetNameGenerator:
    """Generator for creating the target name from an input name.

    Create this class every time when the queue for conversion starts,
    because it remembers all relevant settings to avoid affecting the name
    generation of a running conversion by changing them in the ui.

    This class, once created, can create the names for all conversions in the
    queue, there is no need to create one TargetNameGenerator per Converter.
    """
    def __init__(self):
        # remember settings from when TargetNameGenerator was created:
        settings = get_gio_settings()
        self.same_folder_as_input = settings.get_boolean('same-folder-as-input')
        self.selected_folder = settings.get_string('selected-folder')
        self.output_mime_type = settings.get_string('output-mime-type')
        self.audio_profile = settings.get_string('audio-profile')
        self.vorbis_oga_extension = settings.get_boolean('vorbis-oga-extension')
        self.create_subfolders = settings.get_boolean('create-subfolders')
        self.replace_messy_chars = settings.get_boolean('replace-messy-chars')
        self.subfolder_pattern = get_subfolder_pattern()
        self.basename_pattern = get_basename_pattern()
        self.suffix = get_file_extension(self.output_mime_type)

    @staticmethod
    def _unicode_to_ascii(unicode_string):
        # thanks to http://code.activestate.com/recipes/251871/
        return str(unicodedata.normalize('NFKD', unicode_string).encode('ASCII', 'ignore'), 'ASCII')

    @staticmethod
    def safe_string(name):
        """Replace all special characters in a string.

        Replace all characters that are not ascii, digits or '.' '-' '_' '/'
        with '_'. Umlaute will be changed to their closest non-umlaut
        counterpart.
        """
        nice_chars = string.ascii_letters + string.digits + '.-_/'
        return ''.join([
            c if c in nice_chars else '_' for c in name
        ])

    @staticmethod
    def safe_name(filename, safe_prefix=None):
        """Make a filename without dangerous special characters.

        Replace all characters that are not ascii, digits or '.' '-' '_' '/'
        with '_'. Umlaute will be changed to their closest non-umlaut
        counterpart. Will not be applied on the part of the path that already
        exists, as that part apparently is already safe.

        Parameters
        ----------
        filename : string
            Can be an URI or a normal path
        safe_prefix : string
            Part of filename starting from the beginning of it that should be
            considered safe already and not further modified. Can be None,
            in which case URI parts are detected automatically and preserved.
        """
        if len(filename) == 0:
            raise ValueError('empty filename')

        if safe_prefix is None:
            # the prefix of URIs can be detected automatically.
            safe_prefix = ''
            # don't break 'file:///' or 'ftp://a@b:1/ and keep the original scheme
            # also see https://en.wikipedia.org/wiki/Uniform_Resource_Identifier#Generic_syntax # noqa
            match = split_URI(filename)
            if match[1]:
                # it's an URI!
                safe_prefix = match[1]
                filename = match[3]
                filename = unquote_filename(filename)
        else:
            if not filename.startswith(safe_prefix):
                raise ValueError(
                    'filename {} has to start with safe_prefix {}'.format(
                        filename, safe_prefix
                    )
                )
            filename = filename[len(safe_prefix):]


        # figure out how much of the path already exists
        # split into for example [/test', '/baz.flac'] or ['qux.mp3']
        split = [s for s in re.split(r'((?:/|^)[^/]+)', filename) if s != '']
        safe = ''
        while len(split) > 0:
            part = split.pop(0)
            if os.path.exists(safe + part):
                safe += part
            else:
                # put the remaining unknown non-existing path back together
                # and make it safe
                non_existing = TargetNameGenerator._unicode_to_ascii(
                    part + ''.join(split)
                )
                non_existing = TargetNameGenerator.safe_string(non_existing)
                safe += non_existing
                break

        if safe_prefix:
            safe = safe_prefix + safe
        if '://' in safe:
            safe = filename_to_uri(safe)

        return safe

    def fill_pattern(self, sound_file, pattern):
        """Fill tags into a filename pattern for sound_file.

        Parameters
        ----------
        sound_file : SoundFile
        pattern : string
            complete pattern of the output path
            For example '%(album-artist)s/%(album)s/%(title)s.ogg'
        """
        tags = sound_file.tags

        filename = urllib.parse.unquote(os.path.split(sound_file.uri)[1])
        filename, ext = os.path.splitext(filename)
        d = {
            '.inputname': filename,
            '.ext': ext,
            '.target-ext': self.suffix[1:],
            'album': _('Unknown Album'),
            'artist': _('Unknown Artist'),
            'album-artist': _('Unknown Artist'),
            'title': filename,
            'track-number': 0,
            'track-count': 0,
            'genre': _('Unknown Genre'),
            'year': _('Unknown Year'),
            'date': _('Unknown Date'),
            'album-disc-number': 0,
            'album-disc-count': 0,
        }

        for key in tags:
            d[key] = tags[key]
            if isinstance(d[key], str):
                # take care of tags containing slashes
                d[key] = d[key].replace('/', '-')
                if key.endswith('-number'):
                    d[key] = int(d[key])

        # when artist set & album-artist not, use artist for album-artist
        if 'artist' in tags and 'album-artist' not in tags:
            d['album-artist'] = tags['artist']

        # add timestamp to substitution dict -- this could be split into more
        # entries for more fine-grained control over the string by the user...
        timestamp_string = time.strftime('%Y%m%d_%H_%M_%S')
        d['timestamp'] = timestamp_string

        # now fill the tags in the pattern with values:
        result = pattern % d

        return result

    def generate_temp_path(self, soundfile):
        """Generate a random filename that doesn't exist yet."""
        folder, basename = os.path.split(soundfile.uri)
        if not self.same_folder_as_input:
            folder = self.selected_folder
            folder = urllib.parse.quote(folder, safe='/:@')
        while True:
            rand = str(random())[-6:]
            filename = folder + '/' + basename + '~' + rand + '~SC~'
            if self.replace_messy_chars:
                filename = TargetNameGenerator.safe_name(filename)
            if not vfs_exists(filename):
                return filename

    def generate_target_path(self, sound_file, for_display=False):
        """Generate a target filename in URI format based on the settings.

        Patterns will be populated with tags.

        Parameters
        ----------
        sound_file : SoundFile
        for_display : bool
            Format it nicely in order to print it somewhere
        """
        basename = self.fill_pattern(sound_file, self.basename_pattern)
        subfolder = self.fill_pattern(sound_file, self.subfolder_pattern)

        # the path all soundfiles will have in common
        if self.same_folder_as_input:
            path = sound_file.base_path
        else:
            path = self.selected_folder
        # don't modify that one, becuase it has been selected by the user and
        # already exists.
        safe_prefix = path

        # subfolders that change depending on the soundfile
        if self.create_subfolders:
            path = os.path.join(path, subfolder)
        if sound_file.subfolders is not None and '/' not in basename:
            # use existing subfolders between base_path and the soundfile, but
            # only if the basename_pattern does not create subfolders
            path = os.path.join(path, sound_file.subfolders)

        # filename
        # might actually contain further subfolders by specifying slashes
        path = os.path.join(path, basename)
        path = '{}.{}'.format(path, self.suffix)

        if self.replace_messy_chars:
            path = self.safe_name(path, safe_prefix)

        if for_display:
            return path
        else:
            return filename_to_uri(path)
