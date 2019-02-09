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


import os
import sys
import gi
import time
from gi.repository import GLib

from soundconverter.soundfile import SoundFile
from soundconverter import error
from soundconverter.settings import settings
from soundconverter.gstreamer import TagReader
from soundconverter.namegenerator import TargetNameGenerator
from soundconverter.queue import TaskQueue
from soundconverter.gstreamer import Converter
from soundconverter.fileoperations import unquote_filename, filename_to_uri, vfs_exists


def prepare_files_list(input_files):
    """takes in a list of paths and returns a list of all the files in those
    paths. Also converts the paths to uris.

    Also returns a list of relative directories. This is used to reconstruct
    the directory structure in the output path if -o is provided."""

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
            parsed_files.append(input_path)

        # walk over directories to add the files of all the subdirectories
        elif os.path.isdir(input_path):
            # but only if -r option was provided
            if 'recursive' in settings and settings['recursive']:
                for dirpath, _, filenames in os.walk(input_path):
                    for filename in filenames:
                        if dirpath[-1] != os.sep:
                            dirpath += os.sep
                        parsed_files.append(dirpath + filename)
                        # if input_path is a/b/c/, filename is d.mp3
                        # and dirpath is a/b/c/e/f/, then append e/f/
                        # to subdirectories
                        subdir = os.path.relpath(dirpath, input_path) + os.sep
                        if subdir == './':
                            subdir = ''
                        subdirectories.append(subdir)
            else:
                # else it didn't go into any directory. provide some information about how to
                print(input_path, 'is a directory. Use -r to go into all subdirectories.')
        # if not a file and not a dir it doesn't exist. skip
    parsed_files = list(map(filename_to_uri, parsed_files))

    return parsed_files, subdirectories


def cli_tags_main(input_files):
    """input_files is an array of string paths"""

    input_files, _ = prepare_files_list(input_files)
    error.set_error_handler(error.ErrorPrinter())
    loop = GLib.MainLoop()
    context = loop.get_context()
    for input_file in input_files:
        input_file = SoundFile(input_file)
        if not settings['quiet']:
            print(input_file.filename)
        t = TagReader(input_file)
        t.start()
        while t.running:
            time.sleep(0.01)
            context.iteration(True)
            
        if not settings['quiet']:
            for key in sorted(input_file.tags):
                print(('     %s: %s' % (key, input_file.tags[key])))


class CliProgress:

    def __init__(self):
        self.current_text = ''

    def show(self, new_text):
        if new_text != self.current_text:
            self.clear()
            sys.stdout.write(new_text)
            sys.stdout.flush()
            self.current_text = new_text

    def clear(self):
        sys.stdout.write('\b \b' * len(self.current_text))
        sys.stdout.flush()


def cli_convert_main(input_files):
    """input_files is an array of string paths"""

    input_files, subdirectories = prepare_files_list(input_files)

    loop = GLib.MainLoop()
    context = loop.get_context()
    error.set_error_handler(error.ErrorPrinter())

    output_type = settings['cli-output-type']
    output_suffix = settings['cli-output-suffix']

    generator = TargetNameGenerator()
    generator.suffix = output_suffix

    progress = CliProgress()

    queue = TaskQueue()
    for i, input_file in enumerate(input_files):

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
        if 'ignore-existing' in settings and settings['ignore-existing'] and vfs_exists(output_name):
            print('skipping \'{}\': already exists'.format(unquote_filename(output_name.split(os.sep)[-1][-65:])))
            continue

        if input_file.uri == output_name:
            print('skipping \'{}\': output path is the same as the input path'.format(unquote_filename(output_name.split(os.sep)[-1][-65:])))
            continue

        c = Converter(input_file, output_name, output_type)
        c.overwrite = True
        c.init()
        c.start()
        while c.running:
            if c.get_duration():
                percent = min(100, 100.0* (c.get_position() / c.get_duration()))
                percent = '%.1f %%' % percent
            else:
                percent = '/-\|' [int(time.time()) % 4]
            progress.show('%s: %s' % (unquote_filename(c.sound_file.filename[-65:]), percent ))
            time.sleep(0.01)
            context.iteration(True)
        print()

    previous_filename = None
    
    '''
    queue.start()
    
    #running, progress = queue.get_progress(perfile)
    while queue.running:
        t = None #queue.get_current_task()
        if t and not settings['quiet']:
            if previous_filename != t.sound_file.get_filename_for_display():
                if previous_filename:
                    print _('%s: OK') % previous_filename
                previous_filename = t.sound_file.get_filename_for_display()

            percent = 0
            if t.get_duration():
                percent = '%.1f %%' % ( 100.0* (t.get_position() / t.get_duration() ))
            else:
                percent = '/-\|' [int(time.time()) % 4]
            progress.show('%s: %s' % (t.sound_file.get_filename_for_display()[-65:], percent ))
        time.sleep(0.10)
        context.iteration(True)
    '''
    if not settings['quiet']:
        progress.clear()


