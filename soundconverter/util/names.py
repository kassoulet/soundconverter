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
    unquote_filename
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.formats import get_file_extension
from soundconverter.audio.profiles import audio_profiles_dict


class TargetNameGenerator:
    """Generator for creating the target name from an input name.

    Create this class every time when the queue for conversion starts,
    because it remembers all relevant settings to avoid affecting the name
    generation of a running conversion by changing them in the ui.

    This class, once created, can create the names for all conversions in the
    queue, there is no need to create one TargetNameGenerator per Converter.
    """
    def __init__(self, basename_pattern, subfolder_pattern):
        """
        Parameters
        ----------
        basename_pattern : string
            For example '%(artist)s-%(title)s', without the target extension.
        subfolder_pattern : string
            For example '%(album-artist)s/%(album)s', to create those new
            subfolders in the slected_folder based on tags.
        """
        # TODO keys in gio settings?
        self.basename_pattern = basename_pattern
        self.subfolder_pattern = subfolder_pattern

        config = get_gio_settings()
        self.same_folder_as_input = config.get_boolean('same-folder-as-input')
        self.selected_folder = config.get_string('selected-folder')
        self.output_mime_type = config.get_string('output-mime-type')
        self.audio_profile = config.get_string('audio-profile')
        self.vorbis_oga_extension = config.get_boolean('vorbis-oga-extension')
        self.create_subfolders = config.get_boolean('create-subfolders')
        self.replace_messy_chars = config.get_boolean('replace-messy-chars')

        # figure out the file extension
        suffix = '.{}'.format(get_file_extension(self.output_mime_type))
        self.suffix = suffix

    @staticmethod
    def _unicode_to_ascii(unicode_string):
        # thanks to http://code.activestate.com/recipes/251871/
        return str(unicodedata.normalize('NFKD', unicode_string).encode('ASCII', 'ignore'), 'ASCII')

    @staticmethod
    def safe_name(filename):
        """Make a filename without dangerous special characters.

        Replace all characters that are not ascii, digits or '.' '-' '_' '/'
        with '_'. Umlaute will be changed to their closest non-umlaut
        counterpart. Will not be applied on the part of the path that already
        exists, as that part apparently is already safe.

        Parameters
        ----------
        filename : string
            Can be an URI or a normal path
        """
        if len(filename) == 0:
            raise ValueError('empty filename')

        nice_chars = string.ascii_letters + string.digits + '.-_/'

        scheme = ''
        # don't break 'file://' and keep the original scheme
        match = re.match(r'^([a-zA-Z]+://){0,1}(.+)', filename)
        if match[1]:
            # it's an URI!
            scheme = match[1]
            filename = match[2]
            filename = unquote_filename(filename)

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
                non_existing = ''.join([
                    c if c in nice_chars else '_' for c in non_existing
                ])
                safe += non_existing
                break

        if scheme:
            safe = filename_to_uri(scheme + safe)

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

        _, filename = os.path.split(sound_file.uri)
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

        if self.replace_messy_chars:
            result = self.safe_name(result)

        result = urllib.parse.quote(result, safe='/:%@')
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
        """Generate a target filename based on patterns and settings.

        Parameters
        ----------
        sound_file : SoundFile
        for_display : bool
            Format it nicely in order to print it somewhere
        """
        if self.same_folder_as_input:
            folder = sound_file.base_path
        else:
            folder = self.selected_folder
            folder = urllib.parse.quote(folder, safe='/:@')
            folder = filename_to_uri(folder)

        # pattern contains the complete output path pattern that is yet to be
        # filled with tags.
        # TODO verify if that is proper usage of subfolder_pattern
        if self.create_subfolders:
            pattern = '{}.{}'.format(
                os.path.join(
                    folder, self.subfolder_pattern, self.basename_pattern
                ),
                self.suffix
            )
        else:
            pattern = '{}.{}'.format(
                os.path.join(folder, self.basename_pattern),
                self.suffix
            )

        target_name = self.fill_pattern(sound_file, pattern)
        if for_display:
            return unquote_filename(target_name)
        else:
            return target_name
