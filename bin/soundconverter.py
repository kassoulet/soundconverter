#!/usr/bin/python
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

"""
SoundConverter Launcher.
"""

import os
import sys
import locale
import gettext
from optparse import OptionParser

# variables
LIBDIR = '@libdir@'
DATADIR = '@datadir@'

NAME = 'SoundConverter'
VERSION = '@version@'
print( '%s %s' % (NAME, VERSION) )

GLADEFILE = '@datadir@/soundconverter/soundconverter.glade'

PACKAGE = NAME.lower()
try: 
    locale.setlocale(locale.LC_ALL,'')
    locale.bindtextdomain(PACKAGE,'@datadir@/locale')
    gettext.bindtextdomain(PACKAGE,'@datadir@/locale')
    gettext.textdomain(PACKAGE)
    gettext.install(PACKAGE,localedir='@datadir@/locale',unicode=1)
    #from gettext import gettext as _
except locale.Error:
    print('  cannot use system locale.')
    locale.setlocale(locale.LC_ALL,'C')
    gettext.textdomain(PACKAGE)
    gettext.install(PACKAGE,localedir='@datadir@/locale',unicode=1)

def _add_soundconverter_path():
    global localedir
    root = os.path.join(LIBDIR, 'soundconverter', 'python')

    if not root in sys.path:
        sys.path.insert(0, root)


def _check_libs():
    try:
        import pygtk
        pygtk.require('2.0')
        import gtk
        import gnome
        import gnome.ui
        gnome.ui.authentication_manager_init()
        import gconf
        import gobject
        gobject.threads_init()
        import gnomevfs
    except ImportError, error :
        print('%s needs pygtk and gnome-python >= 2.24! (Error: "%s")' % (NAME, error))
        sys.exit(1)
    except:
        pass

    try:
        import pygst
        pygst.require('0.10')
        import gst
    except ImportError:
        print('%s needs python-gstreamer 0.10!' % NAME)
        sys.exit(1)

    print( '  using Gstreamer version: %s' % (
            '.'.join([str(s) for s in gst.gst_version])) )


def check_mime_type(mime):
    types = {'vorbis': 'audio/x-vorbis', 'flac': 'audio/x-flac', 'wav' : 'audio/x-wav',
        'mp3': 'audio/mpeg', 'aac': 'audio/x-m4a'}
    mime = types.get(mime, mime)
    if mime not in types.values():
        print('Cannot use "%s" mime type.' % mime)
        print 'Supported shortcuts and mime types:',
        for k,v in sorted(types.iteritems()):
            print '%s %s' % (k,v),
        print()
        raise SystemExit
    return mime


def mode_callback(option, opt, value, parser, **kwargs):
    setattr(parser.values, option.dest, kwargs[option.dest])


def parse_command_line():
    parser = OptionParser()
    parser.add_option('-b', '--batch', dest='mode', action='callback',
        callback=mode_callback, callback_kwargs={'mode':'batch'},
        help=_('Convert in batch mode, from command line, '
            'without a graphical user\n interface. You '
            'can use this from, say, shell scripts.'))
    parser.add_option('-t', '--tags', dest="mode", action='callback',
        callback=mode_callback,  callback_kwargs={'mode':'tags'},
        help=_('Show tags for input files instead of converting '
            'them. This indicates \n command line batch mode '
            'and disables the graphical user interface.'))
    parser.add_option('-m', '--mime-type', dest="cli-output-type",
        help=_('Set the output MIME type for batch mode. The default '
            'is %s. Note that you probably want to set the output '
            'suffix as well.') % settings['cli-output-type'])
    parser.add_option('-q', '--quiet', action="store_true", dest="quiet",
        help=_("Be quiet. Don't write normal output, only errors."))
    parser.add_option('-d', '--debug', action="store_true", dest="debug",
        help=_('Displays additional debug information'))
    parser.add_option('-s', '--suffix', dest="cli-output-suffix",
        help=_('Set the output filename suffix for batch mode.'
            'The default is %s . Note that the suffix does not '
            'affect\n the output MIME type.') % settings['cli-output-suffix'])
    parser.add_option('-j', '--jobs', action='store', type='int', dest='jobs',
        metavar='NUM', help=_('Force number of concurrent conversions.'))
    parser.add_option('--help-gst', action="store_true", dest="_unused",
        help=_('Shows GStreamer Options'))
    return parser


_add_soundconverter_path()

import soundconverter
soundconverter.NAME = NAME
soundconverter.VERSION = VERSION
soundconverter.GLADEFILE = GLADEFILE

from soundconverter.settings import settings

parser = parse_command_line()
# remove gstreamer arguments so only gstreamer sees them.
args = [a for a in sys.argv[1:] if '-gst' not in a]

options, files = parser.parse_args(args)

for k in dir(options):
    if k.startswith('_'):
        continue
    if getattr(options, k) is None:
        continue
    settings[k] = getattr(options, k)

settings['cli-output-type'] = check_mime_type(settings['cli-output-type'])

_check_libs()

import gtk
import gtk.glade
gtk.glade.bindtextdomain(PACKAGE, '@datadir@/locale')
gtk.glade.textdomain(PACKAGE)

print('  using %d thread(s)' % settings['jobs'])

from soundconverter.batch import cli_convert_main
from soundconverter.batch import cli_tags_main
from soundconverter.fileoperations import filename_to_uri

files = map(filename_to_uri, files)

try:
    from soundconverter.ui import gui_main
except:
    if settings['mode'] == 'gui':
        settings['mode'] = 'batch'
    
if settings['mode'] == 'gui':
    gui_main(NAME, VERSION, GLADEFILE, files)
elif settings['mode'] == 'tags':
    if not files:
        print('nothing to do...')
    cli_tags_main(files)
else:
    if not files:
        print('nothing to do...')
    cli_convert_main(files)





