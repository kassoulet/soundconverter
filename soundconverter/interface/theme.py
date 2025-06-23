#!/usr/bin/python3
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2025 Gautier Portet
# Copyright 2020-2025 Sezanzeb
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

from gi.repository import Gio, Gtk

gtk_settings = None
gnome_interface_settings = None


def _get_base_theme_name(settings_obj):
    """Helper to get the theme name without -dark or -light suffix."""
    current_theme_name = settings_obj.get_property("gtk-theme-name")
    if current_theme_name.endswith("-dark") or current_theme_name.endswith("-light"):
        return current_theme_name.rsplit("-", 1)[0]
    return current_theme_name


def _apply_theme_preference():
    """Applies the dark/light theme variant based on the current preference from 'color-scheme'."""
    global gtk_settings, gnome_interface_settings

    if gtk_settings is None or gnome_interface_settings is None:
        print(
            "Warning: GSettings not fully initialized for theme preference in _apply_theme_preference."
        )
        return

    # Determine dark preference from 'color-scheme' GSetting
    color_scheme = gnome_interface_settings.get_string("color-scheme")
    prefers_dark = color_scheme == "prefer-dark"

    current_theme_set = gtk_settings.get_property("gtk-theme-name")
    base_theme_name = _get_base_theme_name(gtk_settings)

    target_theme_name = base_theme_name
    if prefers_dark:
        target_theme_name = f"{base_theme_name}-dark"

    # Only set the theme if it's different from the current one to avoid unnecessary calls
    if current_theme_set != target_theme_name:
        gtk_settings.set_property("gtk-theme-name", target_theme_name)


def _on_gtk_theme_name_changed(settings_obj, pspec):
    """Callback when the 'gtk-theme-name' setting itself changes (e.g., user changed it manually)."""
    _apply_theme_preference()


def _on_color_scheme_changed(settings_obj, pspec):
    """Callback for when the 'color-scheme' setting changes."""
    _apply_theme_preference()


def theme_switcher():
    global gtk_settings, gnome_interface_settings
    gtk_settings = Gtk.Settings.get_default()
    gnome_interface_settings = Gio.Settings.new("org.gnome.desktop.interface")

    # Connect signals
    gtk_settings.connect("notify::gtk-theme-name", _on_gtk_theme_name_changed)
    gnome_interface_settings.connect("changed::color-scheme", _on_color_scheme_changed)

    # Apply initial theme preference immediately on startup
    _apply_theme_preference()
