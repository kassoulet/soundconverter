#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2017 Gautier Portet
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

from gi.repository import Gtk, GLib
from soundconverter.soundfile import SoundFile
from soundconverter import error
from soundconverter.settings import settings, get_quality
from soundconverter.gstreamer import TagReader, TypeFinder
from soundconverter.namegenerator import TargetNameGenerator
from soundconverter.queue import TaskQueue
from soundconverter.gstreamer import Converter
from soundconverter.fileoperations import unquote_filename, filename_to_uri, vfs_exists, beautify_uri
from soundconverter.utils import log


def prepare_files_list(input_files):
    """Take in a list of paths and return a list of all the files in those paths, converted to URIs.

    Also returns a list of relative directories. This is used to reconstruct the directory structure in
    the output path if -o is provided.
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
                # else it didn't go into any directory. provide some information about how to
                log(input_path, 'is a directory. Use -r to go into all subdirectories.')
        # if not a file and not a dir it doesn't exist. skip
    parsed_files = list(map(filename_to_uri, parsed_files))

    return parsed_files, subdirectories


def cli_tags_main(input_files):
    """Display all the tags of the specified files in input_files in the console.

    To go into subdirectories of paths provided, the -r command line argument should be provided,
    which is stored in the global 'settings' variable.

    input_files is an array of string paths.
    """
    input_files, _ = prepare_files_list(input_files)
    error.set_error_handler(error.ErrorPrinter())
    loop = GLib.MainLoop()
    context = loop.get_context()
    for input_file in input_files:
        input_file = SoundFile(input_file)
        t = TagReader(input_file)
        t.start()
        while t.running:
            time.sleep(0.01)
            context.iteration(True)

        if len(input_file.tags) > 0:
            log(unquote_filename(input_file.filename))
            for key in sorted(input_file.tags):
                log(('     %s: %s' % (key, input_file.tags[key])))
        else:
            log(unquote_filename(input_file.filename))
            log(('     no tags found'))


class CliProgress:
    """Class to overwrite a progress indication in the console without printing new lines."""

    def __init__(self):
        """Initialize the class without printing anything yet."""
        self.current_text = ''

    def show(self, *msgs):
        """Update the progress in the console.
        
        Example: show(1, "%").
        """
        new_text = ' '.join([str(msg) for msg in msgs])
        if new_text != self.current_text:
            self.clear()
            sys.stdout.write(new_text)
            sys.stdout.flush()
            self.current_text = new_text

    def clear(self):
        """Revert the previously written message. Used in `show`."""
        sys.stdout.write('\b \b' * len(self.current_text))
        sys.stdout.flush()


class CLI_Convert():
    """Main class that runs the conversion."""

    def __init__(self, input_files):
        """Start the conversion of all the files specified in input_files.

        To control the conversion and the handling of directories, command line arguments have to be
        provided which are stored in the global 'settings' variable.

        input_files is an array of string paths.
        """
        # check which files should be converted. The result is
        # stored in file_checker.good_files
        log('\nchecking files and walking dirs in the specified paths…')

        file_checker = CLI_Check(input_files, silent=True)

        # CLI_Check will exit(1) if no input_files available

        # input_files, subdirectories = prepare_files_list(input_files)
        # edit: handled by CLI_Check now
        input_files = file_checker.input_files
        subdirectories = file_checker.subdirectories

        loop = GLib.MainLoop()
        context = loop.get_context()
        error.set_error_handler(error.ErrorPrinter())

        output_type = settings['cli-output-type']
        output_suffix = settings['cli-output-suffix']

        generator = TargetNameGenerator()
        generator.suffix = output_suffix

        conversions = TaskQueue()

        self.started_tasks = 0
        self.num_conversions = 0

        log('\npreparing converters…')
        for i, input_file in enumerate(input_files):

            if input_file not in file_checker.good_files:
                log('skipping \'{}\': invalid soundfile'.format(unquote_filename(input_file.split(os.sep)[-1][-65:])))
                continue

            input_file = SoundFile(input_file)

            if 'output-path' in settings:
                filename = input_file.uri.split(os.sep)[-1]
                output_name = settings['output-path'] + os.sep + subdirectories[i] + filename
                output_name = filename_to_uri(output_name)
                # afterwards set the correct file extension
                if 'cli-output-suffix' in settings:
                    output_name = output_name[:output_name.rfind('.')] + settings['cli-output-suffix']
            else:
                output_name = filename_to_uri(input_file.uri)
                output_name = generator.get_target_name(input_file)

            # skip existing output files if desired (-i cli argument)
            if settings.get('ignore-existing') and vfs_exists(output_name):
                log('skipping \'{}\': already exists'.format(unquote_filename(output_name.split(os.sep)[-1][-65:])))
                continue

            c = Converter(input_file, output_name, output_type)
            c.add_listener('started', self.print_progress)

            if 'quality' in settings:
                quality_setting = settings.get('quality')
                c.set_vorbis_quality(get_quality('vorbis', quality_setting))
                c.set_aac_quality(get_quality('aac', quality_setting))
                c.set_opus_quality(get_quality('opus', quality_setting))
                c.set_mp3_quality(get_quality('mp3', quality_setting))

            c.overwrite = True

            c.init()

            conversions.add_task(c)

            self.num_conversions += 1

        if self.num_conversions == 0:
            log('\nnothing to do…')
            exit(2)

        log('\nstarting conversion…')
        conversions.start()
        while conversions.running:
            # calling this like crazy is the fastest way
            context.iteration(True)

        # do another one to print the queue done message
        context.iteration(True)

    def print_progress(self, c):
        """Print the filename that is currently being converted and how many files are left."""
        self.started_tasks += 1
        path = unquote_filename(beautify_uri(c.sound_file.uri))
        log('{}/{}: \'{}\''.format(self.started_tasks, self.num_conversions, path))


class CLI_Check():

    def __init__(self, input_files, silent=False):
        """Print all the tags of the specified files in input_files to the console.

        To go into subdirectories of paths provided, the -r command line argument should be provided,
        which is stored in the global 'settings' variable.

        input_files is an array of string paths.

        silent=True makes this print no output, no matter the -q argument of soundconverter

        It will exit the tool if input_files contains no files
        (maybe because -r is missing and the specified path is a dir)
        """
        input_files, subdirectories = prepare_files_list(input_files)

        if len(input_files) == 0:
            # prepare_files_list will print something like
            # "use -r to go into subdirectories"
            exit(1)

        # provide this to other code that uses CLI_Check
        self.input_files = input_files
        self.subdirectories = subdirectories

        error.set_error_handler(error.ErrorPrinter())

        typefinders = TaskQueue()

        self.good_files = []

        for input_file in input_files:
            sound_file = SoundFile(input_file)
            typefinder = TypeFinder(sound_file, silent=True)
            typefinder.set_found_type_hook(self.found_type)
            typefinders.add_task(typefinder)

        typefinders.start()
        p = 0
        progress = CliProgress()
        printstepsize = 100/len(input_files)

        loop = GLib.MainLoop()
        context = loop.get_context()

        while typefinders.running:
            if typefinders.progress and typefinders.progress - p > printstepsize:
                p = typefinders.progress
                if not settings.get('quiet'):
                    progress.show('progress: ' + str(round(p*100)) + '%')
            # main_iteration is needed for
            # the typefinder taskqueue to run
            # calling this like crazy is the fastest way
            context.iteration(True)

        # do another one to print the queue done message
        context.iteration(True)

        if not silent:
            log('\nNon-Audio Files:')

            for input_file in input_files:
                if input_file not in self.good_files:
                    log(unquote_filename(beautify_uri(input_file)))

    def found_type(self, sound_file, mime):
        self.good_files.append(sound_file.uri)
