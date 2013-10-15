#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2012 Gautier Portet
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


import sys
import gi
import time
from gi.repository import GObject

from .soundfile import SoundFile
from . import error
from soundconverter.settings import settings
from .gstreamer import TagReader
from .namegenerator import TargetNameGenerator
from .queue import TaskQueue
from .gstreamer import Converter
from .fileoperations import unquote_filename

def cli_tags_main(input_files):
    error.set_error_handler(error.ErrorPrinter())
    loop = GObject.MainLoop()
    context = loop.get_context()
    for input_file in input_files:
        input_file = SoundFile(input_file)
        if not settings['quiet']:
            print((input_file.filename))
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
    loop = GObject.MainLoop()
    context = loop.get_context()
    error.set_error_handler(error.ErrorPrinter())

    output_type = settings['cli-output-type']
    output_suffix = settings['cli-output-suffix']

    generator = TargetNameGenerator()
    generator.suffix = output_suffix

    progress = CliProgress()

    queue = TaskQueue()
    for input_file in input_files:
        input_file = SoundFile(input_file)
        output_name = generator.get_target_name(input_file)
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


