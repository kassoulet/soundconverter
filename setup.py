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

import sys
try:
    import DistUtilsExtra.auto
except ImportError:
    sys.stderr.write('You need python-distutils-extra\n')
    sys.exit(1)

import os
import DistUtilsExtra.auto

# This will automatically, assuming that the prefix is /usr
# - Compile and install po files to /usr/share/locale*.mo,
# - Install .desktop files to /usr/share/applications
# - Install all the py files to /usr/lib/python3.8/site-packages/soundconverter
# - Copy bin to /usr/bin
# - Copy the rest to /usr/share/soundconverter, like the .glade file
# Thanks to DistUtilsExtra (https://salsa.debian.org/python-team/modules/python-distutils-extra/-/tree/master/doc) # noqa


class Install(DistUtilsExtra.auto.install_auto):
    def run(self):
        DistUtilsExtra.auto.install_auto.run(self)
        # after DistUtilsExtra automatically copied data/org.soundconverter.gschema.xml
        # to /usr/share/glib-2.0/schemas/ it doesn't seem to compile them.
        glib_schema_path = os.path.join(self.install_data, 'share/glib-2.0/schemas/')
        cmd = 'glib-compile-schemas {}'.format(glib_schema_path)
        print('running {}'.format(cmd))
        os.system(cmd)


DistUtilsExtra.auto.setup(
    name='soundconverter',
    version='4.0.1',
    description=(
        'A simple sound converter application for the GNOME environment. '
        'It writes WAV, FLAC, MP3, and Ogg Vorbis files.'
    ),
    license='GPL-3.0',
    data_files=[
        ('share/metainfo/', ['data/soundconverter.appdata.xml']),
        ('share/pixmaps/', ['data/soundconverter.png']),
        ('share/icons/hicolor/scalable/apps/', ['data/soundconverter.svg'])
    ],
    cmdclass={
        'install': Install
    }
)
