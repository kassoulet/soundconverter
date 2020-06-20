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

"""SoundConverter Launcher."""

# imports and package setup

import os
import sys
import locale
import gettext
from optparse import OptionParser, OptionGroup

# variables
LIBDIR = '@libdir@'
DATADIR = '@datadir@'
NAME = 'SoundConverter'
VERSION = '@version@'
GLADEFILE = '@datadir@/soundconverter/soundconverter.glade'
PACKAGE = NAME.lower()

try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gst, Gtk, GLib, Gdk
except (ImportError, ValueError) as error:
    print(('%s needs GTK >= 3.0 (Error: "%s")' % (NAME, error)))
    sys.exit(1)

# remove gstreamer arguments so only gstreamer sees them. See `gst-launch-1.0 --help-gst`
# and https://gstreamer.freedesktop.org/documentation/application-development/appendix/checklist-element.html
args = [a for a in sys.argv[1:] if not a.startswith('--gst-')]
Gst.init([None] + [a for a in sys.argv[1:] if a.startswith('--gst-')])

try:
    locale.setlocale(locale.LC_ALL, '')
    locale.bindtextdomain(PACKAGE, '@datadir@/locale')
    gettext.bindtextdomain(PACKAGE, '@datadir@/locale')
    gettext.textdomain(PACKAGE)
    gettext.install(PACKAGE, localedir='@datadir@/locale')
    # rom gettext import gettext as _
except locale.Error:
    print('cannot use system locale.')
    locale.setlocale(locale.LC_ALL, 'C')
    gettext.textdomain(PACKAGE)
    gettext.install(PACKAGE, localedir='@datadir@/locale')


def _add_soundconverter_path():
    """Make the soundconverter package importable, which has been installed to LIBDIR during make install."""
    root = os.path.join(LIBDIR, 'soundconverter', 'python')
    if root not in sys.path:
        sys.path.insert(0, root)


_add_soundconverter_path()
import soundconverter
soundconverter.NAME = NAME
soundconverter.VERSION = VERSION
soundconverter.GLADEFILE = GLADEFILE
from soundconverter.settings import settings
from soundconverter.fileoperations import vfs_encode_filename
from soundconverter.batch import CLI_Convert, cli_tags_main, CLI_Check
from soundconverter.fileoperations import filename_to_uri
from soundconverter.ui import gui_main
from soundconverter.utils import logger, update_verbosity

# command line argument parsing, launch-mode


def check_mime_type(mime):
    types = {
        'vorbis': 'audio/x-vorbis', 'flac': 'audio/x-flac', 'wav': 'audio/x-wav',
        'mp3': 'audio/mpeg', 'aac': 'audio/x-m4a'
    }
    mime = types.get(mime, mime)
    if mime not in list(types.values()):
        logger.info(('Cannot use "%s" mime type.' % mime))
        msg = 'Supported shortcuts and mime types:'
        for k, v in sorted(types.items()):
            msg += ' %s %s' % (k, v)
        logger.info(msg)
        raise SystemExit
    return mime


def mode_callback(option, opt, value, parser, **kwargs):
    setattr(parser.values, option.dest, kwargs[option.dest])


class ModifiedOptionParser(OptionParser):
    """An OptionParser class that doesn't remove newlines on the epilog in order to show usage examples.
    
    https://stackoverflow.com/questions/1857346/

    See optparse.OptionParser for the original docstring
    """
    
    def format_epilog(self, formatter):
        if self.epilog is None:
            return ""
        return self.epilog


def parse_command_line():
    """Create and return the OptionParser, which parse the command line arguments and displays help with --help."""
    parser = ModifiedOptionParser(
        epilog='\nExample:\n'
        '  soundconverter -b [file] [dir] -r -m audio/x-vorbis -s .ogg -o [output dir] -Q 4\n'
    )

    parser.add_option(
        '-c', '--check', dest='mode', action='callback',
        callback=mode_callback, callback_kwargs={'mode': 'check'},
        help=_(
            'log which files cannot be read by gstreamer. '
            'Useful before converting. This will disable the GUI and '
            'run in batch mode, from the command line.'
        )
    )
    parser.add_option(
        '-b', '--batch', dest='mode', action='callback',
        callback=mode_callback, callback_kwargs={'mode': 'batch'},
        help=_(
            'Convert in batch mode, from the command line, '
            'without a graphical user interface. You '
            'can use this from, say, shell scripts.'
        )
    )
    parser.add_option(
        '-t', '--tags', dest="mode", action='callback',
        callback=mode_callback,  callback_kwargs={'mode': 'tags'},
        help=_(
            'Show tags for input files instead of converting '
            'them. This indicates command line batch mode '
            'and disables the graphical user interface.'
        )
    )
    parser.add_option(
        '-q', '--quiet', action="store_true", dest="quiet",
        help=_("Be quiet. Don't write normal output, only errors.")
    )
    parser.add_option(
        '-d', '--debug', action="store_true", dest="debug",
        help=_('Displays additional debug information')
    )
    parser.add_option(
        '-j', '--jobs', action='store', type='int', dest='forced-jobs',
        metavar='NUM', help=_('Force number of concurrent conversions.')
    )

    # batch mode settings
    batch_option_group = OptionGroup(
        parser, 'Batch Mode Options',
        'Those options will only have effect when the -b, -c or -t '
        'option is provided'
    )
    batch_option_group.add_option(
        '-m', '--mime-type', dest="cli-output-type",
        help=_(
            'Set the output MIME type. The default '
            'is %s. Note that you will probably want to set the output '
            'suffix as well. Supported MIME types: %s'
        ) % (
            settings['cli-output-type'],
            'audio/x-m4a (AAC) audio/x-flac (FLAC) audio/mpeg (MP3) audio/x-vorbis (Vorbis)'
            'audio/x-wav (WAV)'
        )
    )
    batch_option_group.add_option(
        '-s', '--suffix', dest="cli-output-suffix",
        help=_(
            'Set the output filename suffix. '
            'The default is %s. Note that the suffix does not '
            'affect\n the output MIME type.'
        ) % settings['cli-output-suffix']
    )
    batch_option_group.add_option(
        '-r', '--recursive', action="store_true", dest="recursive",
        help=_('Go recursively into subdirectories')
    )
    batch_option_group.add_option(
        '-i', '--ignore', action="store_true", dest="ignore-existing",
        help=_(
            'Ignore files for which the target already exists instead '
            'of converting them again'
        )
    )
    batch_option_group.add_option(
        '-o', '--output', action="store", dest="output-path",
        help=_(
            'Put converted files into a different directory while rebuilding '
            'the original directory structure. This includes the name of the original '
            'directory.'
        )
    )
    batch_option_group.add_option(
        '-Q', '--quality', action="store", type='int', dest="quality",
        metavar='NUM', help=_(
                'Quality of the converted output file. Between 0 '
                '(lowest) and 5 (highest). Default is 3.'
            ),
        default=3
    )

    parser.add_option_group(batch_option_group)

    # not implemented yet
    # parser.add_option('--help-gst', action="store_true", dest="_unused",
    #     help=_('Shows GStreamer Options'))

    return parser


parser = parse_command_line()

options, files = parser.parse_args(args)

for k in dir(options):
    if k.startswith('_'):
        continue
    if getattr(options, k) is None:
        continue
    settings[k] = getattr(options, k)

settings['cli-output-type'] = check_mime_type(settings['cli-output-type'])

update_verbosity()

if not settings.get('quiet'):
    logger.info(('%s %s' % (NAME, VERSION)))
    if settings['forced-jobs']:
        logger.info(('Using %d thread(s)' % settings['forced-jobs']))

if settings['mode'] == 'gui':
    gui_main(NAME, VERSION, GLADEFILE, files)
else:
    if not files:
        logger.info('nothing to do…')
    if settings['mode'] == 'tags':
        cli_tags_main(files)
    elif settings['mode'] == 'batch':
        CLI_Convert(files)
    elif settings['mode'] == 'check':
        CLI_Check(files)
