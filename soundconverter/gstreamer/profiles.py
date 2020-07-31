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


# load gstreamer audio profiles
_GCONF_PROFILE_PATH = "/system/gstreamer/1.0/audio/profiles/"
_GCONF_PROFILE_LIST_PATH = "/system/gstreamer/1.0/audio/global/profile_list"
audio_profiles_list = []
audio_profiles_dict = {}

try:
    import gi
    gi.require_version('GConf', '2.0')
    from gi.repository import GConf
    _GCONF = GConf.Client.get_default()
    profiles = _GCONF.all_dirs(_GCONF_PROFILE_LIST_PATH)
    for name in profiles:
        if _GCONF.get_bool(_GCONF_PROFILE_PATH + name + "/active"):
            # get profile
            description = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/name")
            extension = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/extension")
            pipeline = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/pipeline")
            # check profile validity
            if not extension or not pipeline:
                continue
            if not description:
                description = extension
            if description in audio_profiles_dict:
                continue
                # store
            profile = description, extension, pipeline
            audio_profiles_list.append(profile)
            audio_profiles_dict[description] = profile
except (ImportError, ValueError):
    pass
