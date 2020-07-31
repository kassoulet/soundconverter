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

"""Batch mode to run soundconverter in a console."""

import os
import sys
import time

from gi.repository import GLib, Gio
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.settings import settings, set_gio_settings, \
    get_gio_settings
from soundconverter.util.formats import get_quality_setting_name, \
    get_mime_type, get_mime_type_mapping
from soundconverter.gstreamer.converter import Converter
from soundconverter.gstreamer.discoverer import Discoverer
from soundconverter.gstreamer.taskqueue import TaskQueue
from soundconverter.util.namegenerator import TargetNameGenerator
from soundconverter.util.fileoperations import unquote_filename, \
    filename_to_uri, beautify_uri
from soundconverter.util.logger import logger


def use_memory_gsettings(options):
    """Use a Gio memory backend and write argv settings into it.

    In order for the batch mode to work properly with functions that were
    written for the ui, write argv into the gio settings, but provide a
    temporary memory backend so that the ui keeps its settings and cli
    settings are thrown away at the end.
    """
    backend = Gio.memory_settings_backend_new()
    gio_settings = Gio.Settings.new_with_backend('org.soundconverter', backend)
    set_gio_settings(gio_settings)

    # the number of jobs is only applied, when limit-jobs is true
    forced_jobs = options.get('forced-jobs', None)
    if forced_jobs is not None:
        gio_settings.set_boolean('limit-jobs', True)
        gio_settings.set_int('number-of-jobs', options['forced-jobs'])
    else:
        gio_settings.set_boolean('limit-jobs', False)

    mime_type = get_mime_type(options['format'])
    gio_settings.set_string('output-mime-type', mime_type)

    output_path = filename_to_uri(options['output-path'])
    gio_settings.set_string('selected-folder', output_path)

    gio_settings.set_boolean('same-folder-as-input', False)

    # enable custom patterns by setting the index to the last entry
    gio_settings.set_int('subfolder-pattern-index', -1)


def validate_args(options):
    """Check if required command line args are provided."""
    if options['output-path'] is None:
        logger.error('output path argument -o is required')
        raise SystemExit

    mime = options['format']
    if mime is None:
        logger.error('format argument -f is required')
        raise SystemExit
    mime = get_mime_type(mime)
    if mime is None:
        logger.error('Cannot use "{}" mime type.'.format(mime))
        msg = 'Supported shortcuts and mime types:'
        for k, v in sorted(get_mime_type_mapping().items()):
            msg += ' {} {}'.format(k, v)
        logger.info(msg)
        raise SystemExit


def prepare_files_list(input_files):
    """Create a list of all URIs in a list of paths.

    Also returns a list of relative directories. This is used to reconstruct
    the directory structure in
    the output path if -o is provided.

    Parameters
    ----------
    input_files : string[]
        Array of paths
    """
    # The GUI has its own way of going through subdirectories.
    # Provide similar functionality to the cli.
    # If one of the files is a directory, walk over the files in that
    # and append each one to parsed_files if -r is provided.
    subdirectories = []
    parsed_files = []
    for input_path in input_files:
        # accept tilde (~) to point to home directories
        if input_path[0] == '~':
            input_path = os.getenv('HOME') + input_path[1:]

        if os.path.isfile(input_path):
            # for every appended file, also append to
            # subdirectories
            subdirectories.append('')
            parsed_files.append(input_path)

        # walk over directories to add the files of all the subdirectories
        elif os.path.isdir(input_path):

            if input_path[-1] == os.sep:
                input_path = input_path[:-1]

            parent = input_path[:input_path.rfind(os.sep)]

            # but only if -r option was provided
            if settings.get('recursive'):
                for dirpath, _, filenames in os.walk(input_path):
                    for filename in filenames:
                        if dirpath[-1] != os.sep:
                            dirpath += os.sep
                        parsed_files.append(dirpath + filename)
                        # if input_path is a/b/c/, filename is d.mp3
                        # and dirpath is a/b/c/e/f/, then append c/e/f/
                        # to subdirectories.
                        # The root might be different for various files because
                        # multiple paths can be provided in the args. Hence
                        # this is needed.
                        subdir = os.path.relpath(dirpath, parent) + os.sep
                        if subdir == './':
                            subdir = ''
                        subdirectories.append(subdir)
            else:
                # else it didn't go into any directory.
                # Provide some information about how to
                logger.error(
                    '{} is a directory. Use -r to go into all subdirectories.'
                    .format(input_path)
                )
        # if not a file and not a dir it doesn't exist. skip

    parsed_files = list(map(filename_to_uri, parsed_files))

    return parsed_files, subdirectories


class CLIConvert:
    """Main class that runs the conversion."""

    def __init__(self, input_files):
        """Start the conversion of all the files specified in input_files.

        To control the conversion and the handling of directories, command
        line arguments have to be provided which are stored in the global
        'settings' variable.

        input_files is an array of string paths.
        """
        logger.info(
            '\nchecking files and walking dirs in the specified paths…'
        )

        # CLICheck will exit(1) if no input_files available and resolve
        # all files in input_files and also figure out which files can be
        # converted.
        file_checker = CLICheck(input_files)
        input_files = file_checker.input_files

        loop = GLib.MainLoop()
        context = loop.get_context()

        name_generator = TargetNameGenerator()
        suffix = name_generator.suffix
        name_generator.suffix = suffix

        conversions = TaskQueue()

        self.started_tasks = 0
        self.num_conversions = 0

        logger.info('\npreparing converters…')
        for i, input_file in enumerate(input_files):
            if input_file not in file_checker.get_audio_uris():
                filename = beautify_uri(input_file)
                logger.info(
                    'skipping \'{}\': not an audiofile'.format(filename)
                )
                continue

            input_file = SoundFile(input_file)

            output_uri = name_generator.generate_target_path(input_file)

            c = Converter(input_file, output_uri, name_generator)

            if 'quality' in settings:
                quality_setting = settings.get('quality')
                setting_name = get_quality_setting_name()
                get_gio_settings().set_value(setting_name, quality_setting)

            c.overwrite = True

            conversions.add(c)

            self.num_conversions += 1

        if self.num_conversions == 0:
            logger.info('\nnothing to do…')
            exit(2)

        logger.info('\nstarting conversion…')
        conversions.run()
        while conversions.running:
            # make the eventloop of glibs async stuff run until finished:
            context.iteration(True)

        # do another one to print the queue done message
        context.iteration(True)

    def print_progress(self, c):
        """Print the current filename and how many files are left."""
        self.started_tasks += 1
        path = unquote_filename(beautify_uri(c.sound_file.uri))
        logger.info('{}/{}: \'{}\''.format(
            self.started_tasks, self.num_conversions, path)
        )


class CLICheck:
    """Print all the tags of the specified files to the console."""

    def __init__(
            self, input_files, print_readable=False, print_tags=False,
            print_not_readable=False
    ):
        """Print all the tags of the specified files to the console.

        To go into subdirectories of paths provided, the -r command line
        argument should be provided, which is stored in the global 'settings'
        variable.

        It will exit soundconverter if input_files contains no files
        (maybe because -r is missing and the specified path is a dir)

        Parameters
        ----------
        input_files : string[]
            an array of string paths.
        print_readable : bool
            if False, will print nothing at all
        print_tags : bool
            if True, will print tags
        print_not_readable : bool
            if True, will also print when a file is not an audiofile
        """
        self.print_tags = print_tags
        self.print_not_readable = print_not_readable

        input_files, subdirectories = prepare_files_list(input_files)

        if len(input_files) == 0:
            # prepare_files_list will print something like
            # "use -r to go into subdirectories"
            exit(1)

        # provide this to other code that uses CLICheck
        self.input_files = input_files
        self.subdirectories = subdirectories

        typefinders = TaskQueue()
        for input_file in input_files:
            typefinders.add(Discoverer(SoundFile(input_file)))
        typefinders.run()

        loop = GLib.MainLoop()
        context = loop.get_context()

        while not typefinders.finished:
            # main_iteration is needed for the typefinder taskqueue to run
            # calling this like crazy is the fastest way
            context.iteration(True)

        self.discoverers = typefinders.done

        if print_readable:
            for discoverer in self.discoverers:
                sound_file = discoverer.sound_file
                if sound_file.readable:
                    self.print(sound_file)
                elif self.print_not_readable:
                    logger.info('{} is not an audiofile'.format(
                        unquote_filename(beautify_uri(sound_file.uri)))
                    )

    def get_audio_uris(self):
        """Get a list of all SoundFile objects that can be converted."""
        return [
            discoverer.sound_file.uri for discoverer in self.discoverers
            if discoverer.readable
        ]

    def print(self, sound_file):
        """Print tags of a file, or write that it doesn't have tags."""
        logger.info(unquote_filename(sound_file.filename))

        if self.print_tags:
            if len(sound_file.tags) > 0:
                for key in sorted(sound_file.tags):
                    logger.info(('    {}: {}'.format(key, sound_file.tags[key])))
            else:
                logger.info(('    no tags found'))
