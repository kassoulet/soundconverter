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

from gi.repository import GLib, Gio

from soundconverter.util.soundfile import SoundFile
from soundconverter.util.settings import settings, set_gio_settings
from soundconverter.util.formats import get_quality_setting_name, \
    get_mime_type, get_mime_type_mapping, get_default_quality
from soundconverter.gstreamer.converter import Converter
from soundconverter.gstreamer.discoverer import add_discoverers, \
    get_sound_files
from soundconverter.util.taskqueue import TaskQueue
from soundconverter.util.namegenerator import TargetNameGenerator
from soundconverter.util.fileoperations import filename_to_uri, beautify_uri
from soundconverter.util.logger import logger
from soundconverter.util.formatting import format_time

cli_convert = [None]


def batch_main(files):
    global cli_convert
    # works like a pointer, so that it can be accessed in tests,
    # just like in ui.py
    cli_convert[0] = CLIConvert(files)


def use_memory_gsettings(options):
    """Use a Gio memory backend and write argv settings into it.

    In order for the batch mode to work properly with functions that were
    written for the ui, write argv into the gio settings, but provide a
    temporary memory backend so that the ui keeps its settings and cli
    settings are thrown away at the end.
    """
    if options.get('main') == 'gui':
        raise AssertionError('should not be used with the gui mode')

    backend = Gio.memory_settings_backend_new()
    gio_settings = Gio.Settings.new_with_backend('org.soundconverter', backend)
    set_gio_settings(gio_settings)

    gio_settings.set_boolean('delete-original', False)

    if options.get('main') == 'batch':
        # the number of jobs is only applied, when limit-jobs is true
        forced_jobs = options.get('forced-jobs', None)
        if forced_jobs is not None:
            gio_settings.set_boolean('limit-jobs', True)
            gio_settings.set_int('number-of-jobs', options['forced-jobs'])
        else:
            gio_settings.set_boolean('limit-jobs', False)

        format_option = options['format']
        mime_type = get_mime_type(format_option)

        mode = options.get('mode')
        if mode:
            gio_settings.set_string('mp3-mode', mode)

        gio_settings.set_string('output-mime-type', mime_type)

        output_path = filename_to_uri(options.get('output-path'))
        gio_settings.set_string('selected-folder', output_path)

        gio_settings.set_boolean('same-folder-as-input', False)

        # other than the ui, the batch mode doesn't have a selection of
        # predefined patterns and it's all text anyways, so patterns can be
        # created with the -p argument on custom-filename-pattern. Don't use
        # -o for that to avoid having to escape pattern symbols when a folder
        # is called like a pattern string.
        gio_settings.set_boolean('create-subfolders', False)
        pattern = options.get('custom-filename-pattern')
        if pattern:
            gio_settings.set_int('name-pattern-index', -1)
            gio_settings.set_string('custom-filename-pattern', pattern)
        else:
            # the first name pattern is the filename itself
            gio_settings.set_int('name-pattern-index', 0)

        quality_setting = options.get('quality')
        if quality_setting is None:
            quality_setting = get_default_quality(mime_type)

        setting_name = get_quality_setting_name()
        # here is the very long and incredible way to set a variable as gio
        # settings value with the correct type as defined in the schema:
        type_string = gio_settings \
            .props \
            .settings_schema \
            .get_key(setting_name) \
            .get_value_type() \
            .dup_string()
        variant = GLib.Variant(type_string, float(quality_setting))
        gio_settings.set_value(
            setting_name,
            variant
        )

    else:
        # --tags and --check
        gio_settings.set_boolean('limit-jobs', True)
        gio_settings.set_int('number-of-jobs', 1)


def validate_args(options):
    """Check if required command line args are provided.

    Will log usage mistakes to the console.
    """
    main = options.get('main', 'gui')
    if main not in ['gui', 'check', 'tags', 'batch']:
        logger.error('unknown main {}'.format(main))
        return False

    if main not in ['gui', 'check', 'tags']:
        # not needed for --check and --tags
        if not options.get('output-path'):
            logger.error('output path argument -o is required')
            return False

        existing_behaviour = options.get('existing')
        if existing_behaviour:
            existing_behaviours = [
                Converter.SKIP, Converter.OVERWRITE, Converter.INCREMENT
            ]
            if existing_behaviour not in existing_behaviours:
                logger.error('-e should be one of {}'.format(
                    ', '.join(existing_behaviours)
                ))
                return False

        # target_format might be a mime type or a file extension
        target_format = options.get('format')
        if target_format is None:
            logger.error('format argument -f is required')
            return False
        mime_type = get_mime_type(target_format)
        if mime_type is None:
            logger.error(
                'cannot use "{}" format. Supported formats: {}'.format(
                    target_format,
                    ', '.join(get_mime_type_mapping())
                )
            )
            return False

        mode = options.get('mode')
        if mode and mode not in ['abr', 'cbr', 'vbr']:
            logger.error('mode should be one of abr, cbr or vbr (default)')
            return False

        # validate if the quality setting makes sense
        quality = options.get('quality')

        if quality is not None:
            # optional; otherwise default quality values will be used
            if mime_type == 'audio/mpeg':
                if mode in ['abr', 'cbr']:
                    if quality > 320 or quality < 64:
                        logger.error(
                            'mp3 cbr/abr bitrate should be between 64 and 320'
                        )
                        return False
                else:
                    if quality > 9 or quality < 0:
                        logger.error(
                            'mp3 vbr quality should be between 9 (low) and '
                            '0 (hight)'
                        )
                        return False

            elif mime_type == 'audio/x-vorbis':
                if quality < 0 or quality > 1:
                    logger.error('ogg quality should be between 0.0 and 1.0')
                    return False

            elif mime_type == 'audio/x-m4a':
                if quality < 0 or quality > 400:
                    logger.error('m4a bitrate should be between 0 and 400')
                    return False

            elif mime_type == 'audio/x-flac':
                if quality < 0 or quality > 8:
                    logger.error(
                        'flac compression strength should be between 0 and 8'
                    )
                    return False

            elif mime_type == 'audio/x-wav':
                if quality not in [8, 16, 24, 32]:
                    logger.error(
                        'wav sample width has to be one of 8, 16, 24 or 32'
                    )
                    return False

            elif mime_type == 'audio/ogg; codecs=opus':
                # source: https://wiki.hydrogenaud.io/index.php?title=Opus
                if quality < 6 or quality > 510:
                    logger.error('opus bitrate should be between 6 and 510')
                    return False

    return True


def prepare_files_list(input_files):
    """Create a list of all URIs in a list of paths.

    Also returns a list of relative directories. This is used to reconstruct
    the directory structure in the output path.

    If input_path is a/b/c/ and the file is at a/b/c/e/f/d.mp3,
    the subdirectries entry will be subdirectories c/e/f/.

    If input_files is ['/a/b', '/c']
    and files are found at ['file:///a/b/d.mp3', '[file:///c/e/f/g.mp3'],
    subdirectories will be ['b/d', 'c/e/f']

    Subdirectories might be different for various files because
    multiple paths can be provided in the args.

    Parameters
    ----------
    input_files : string[]
        Array of paths (not uris)
    """
    # The GUI has its own way of going through subdirectories.

    # If one of the files is a directory, walk over the files in that
    # and append each one to parsed_files if -r is provided.
    subdirectories = []
    parsed_files = []
    for input_path in input_files:
        # accept tilde (~) to point to home directories, get absolute path
        input_path = os.path.realpath(os.path.expanduser(input_path))

        if os.path.isfile(input_path):
            # for every appended file, also append to
            # subdirectories
            subdirectories.append('')
            parsed_files.append(input_path)

        # walk over directories to add the files of all the subdirectories
        elif os.path.isdir(input_path):
            if input_path[-1] == os.sep:
                input_path = input_path[:-1]

            if input_path.rfind(os.sep) != -1:
                parent = input_path[:input_path.rfind(os.sep)]
            else:
                parent = input_path

            # but only if -r option was provided
            if settings.get('recursive'):
                for dirpath, _, filenames in os.walk(input_path):
                    for filename in filenames:
                        if dirpath[-1] != os.sep:
                            dirpath += os.sep
                        # dirpath: for example a/b/c/e/f/
                        parsed_files.append(dirpath + filename)
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
            'checking files and walking dirs in the specified paths…'
        )

        # CLICheck will exit(1) if no input_files available and resolve
        # all files in input_files and also figure out which files can be
        # converted.
        file_checker = CLICheck(input_files)

        loop = GLib.MainLoop()
        context = loop.get_context()

        name_generator = TargetNameGenerator()
        suffix = name_generator.suffix
        name_generator.suffix = suffix

        conversions = TaskQueue()

        self.started_tasks = 0
        self.num_conversions = 0

        sound_files = file_checker.get_sound_files()
        for sound_file in sound_files:
            if not sound_file.readable:
                filename = beautify_uri(sound_file.uri)
                logger.info(
                    'skipping \'{}\': not an audiofile'.format(filename)
                )
                continue

            converter = Converter(sound_file, name_generator)

            converter.existing_behaviour = settings.get('existing')

            conversions.add(converter)

            self.num_conversions += 1

        if self.num_conversions == 0:
            logger.info('no audio files for conversion found…')
            exit(2)

        logger.info('starting conversion of {} files…'.format(
            len(sound_files)
        ))
        self.conversions = conversions
        conversions.run()
        while conversions.running:
            # make the eventloop of glibs async stuff run until finished:
            context.iteration(True)

        # do another one to print the queue done message
        context.iteration(True)

        total_time = conversions.get_duration()
        logger.info('converted {} files in {}'.format(
            len(sound_files),
            format_time(total_time)
        ))


class CLICheck:
    """Print all the tags of the specified files to the console."""

    def __init__(
            self, input_files, verbose=False
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
        verbose : bool
            if True, will print tags, readable and non readable paths
        """

        input_files, subdirectories = prepare_files_list(input_files)

        if len(input_files) == 0:
            # prepare_files_list will print something like
            # "use -r to go into subdirectories"
            logger.info('no files found…')
            exit(1)

        discoverers = TaskQueue()
        sound_files = []
        for subdirectory, input_file in zip(subdirectories, input_files):
            sound_file = SoundFile(input_file)
            # by storing it in subfolders, the original subfolder structure
            # (relative to the directory that was provided as input in the
            # cli) can be restored in the target dir
            sound_file.subfolders = subdirectory
            sound_files.append(sound_file)

        add_discoverers(discoverers, sound_files)
        discoverers.run()

        loop = GLib.MainLoop()
        context = loop.get_context()

        while not discoverers.finished:
            # main_iteration is needed for the typefinder taskqueue to run
            # calling this like crazy is the fastest way
            context.iteration(True)

        self.discoverers = discoverers.all_tasks
        sound_files = []
        for discoverer in self.discoverers:
            sound_files += discoverer.sound_files

        if verbose:
            for sound_file in sound_files:
                if sound_file.readable:
                    self.print(sound_file)
                else:
                    logger.info('{} is not an audiofile'.format(
                        beautify_uri(sound_file.uri)
                    ))

    def get_sound_files(self):
        """Get all SoundFiles."""
        return get_sound_files(self.discoverers)

    def print(self, sound_file):
        """Print tags of a file, or write that it doesn't have tags."""
        logger.info(beautify_uri(sound_file.uri))

        if len(sound_file.tags) > 0:
            for key in sorted(sound_file.tags):
                value = sound_file.tags[key]
                logger.info(('    {}: {}'.format(key, value)))
        else:
            logger.info(('    no tags found'))
