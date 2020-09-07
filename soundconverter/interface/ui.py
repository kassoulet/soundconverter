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

import os
import sys
from gettext import gettext as _

from gi.repository import Gtk, GLib

from soundconverter.util.fileoperations import filename_to_uri
from soundconverter.util.settings import settings
from soundconverter.util.namegenerator import TargetNameGenerator, \
    filepattern
from soundconverter.util.taskqueue import TaskQueue
from soundconverter.util.logger import logger
from soundconverter.gstreamer.converter import Converter
from soundconverter.util.error import set_error_handler
from soundconverter.util.formatting import format_time
from soundconverter.interface.filelist import FileList
from soundconverter.interface.gladewindow import GladeWindow
from soundconverter.interface.preferences import PreferencesDialog
from soundconverter.interface.mainloop import gtk_sleep, gtk_iteration


class ErrorDialog:
    def __init__(self, builder):
        self.dialog = builder.get_object('error_dialog')
        self.dialog.set_transient_for(builder.get_object('window'))
        self.primary = builder.get_object('primary_error_label')
        self.secondary = builder.get_object('secondary_error_label')

    def show_error(self, primary, secondary):
        self.primary.set_markup(str(primary))
        self.secondary.set_markup(str(secondary))
        try:
            sys.stderr.write(_('\nError: %s\n%s\n') % (primary, secondary))
        except Exception:
            pass
        self.dialog.run()
        self.dialog.hide()


class ProgressBar:
    """Wrapper for the progressbar to enable smoothing.

    Because changes only arrive every second which makes the progress jump
    for a small number of files.
    """
    def __init__(self, progressbar, period=1):
        """Initialize the fraction object without doing anything yet.

        Parameters
        ----------
        period : int
            How fast new fraction values are expected to arrive in seconds.
            Doesn't have to be accurate.
        """
        self.progressbar = progressbar
        self.steps = 0
        self.period = period
        self.current_fraction = 0
        self.fraction_target = 0
        self.step = 0
        self.timeout_id = None
        self.progressbar.set_fraction(0)

    def __getattr__(self, attribute):
        """For all other attributes, try to get them from the widget."""
        return getattr(self.progressbar, attribute)

    def set_fraction(self, fraction):
        """Set a fraction that will be shown after interpolating to it."""
        fraction = min(1, max(0, fraction))
        if fraction in [0, 1]:
            self.set_current(fraction)
            return

        self.fraction_target = fraction
        difference = self.fraction_target - self.current_fraction

        if difference <= 0:
            self.set_current(fraction)
            return

        # not more steps than the progressbar can resolute
        # and not more than 30 fps
        self.steps = min(
            30 * self.period,
            round(self.progressbar.get_allocated_width() * difference)
        )

        # don't make an interval if not needed
        if self.steps <= 1:
            self.set_current(fraction)
            return

        # restart the interpolation
        self.step = 0
        interval = 1000 * self.period / self.steps
        if self.timeout_id is not None:
            GLib.Source.remove(self.timeout_id)
        self.timeout_id = GLib.timeout_add(interval, self.interpolate)

    def get_fraction(self):
        return self.current_fraction

    def set_current(self, new_fraction):
        """Set the value immediatelly without interpolating it."""
        if new_fraction != self.current_fraction:
            self.progressbar.set_fraction(new_fraction)
            self.current_fraction = new_fraction

    def interpolate(self):
        """Take a small step from the previous fraction to the target."""
        if self.fraction_target in [0, 1]:
            self.set_current(self.fraction_target)
            self.timeout_id = None
            return False

        difference = self.fraction_target - self.current_fraction
        change = difference / max(1, self.steps - self.step)
        self.step += 1
        new_fraction = self.current_fraction + change
        self.set_current(new_fraction)

        if self.step >= self.steps:
            # wait before starting the interpolation timeout again
            self.timeout_id = None
            return False

        return True


class SoundConverterWindow(GladeWindow):
    """Main application class."""

    sensitive_names = [
        'remove', 'clearlist',
        'convert_button'
    ]
    unsensitive_when_converting = [
        'remove', 'clearlist', 'prefs_button',
        'toolbutton_addfile', 'toolbutton_addfolder', 'convert_button',
        'filelist', 'menubar'
    ]

    def __init__(self, builder):
        GladeWindow.__init__(self, builder)

        self.widget = builder.get_object('window')
        self.prefs = PreferencesDialog(builder, self.widget)
        GladeWindow.connect_signals()

        self.filelist = FileList(self, builder)
        self.filelist_selection = self.filelist.widget.get_selection()
        self.filelist_selection.connect('changed', self.selection_changed)
        self.existsdialog = builder.get_object('existsdialog')
        self.existsdialog.message = builder.get_object('exists_message')
        self.existsdialog.apply_to_all = builder.get_object('apply_to_all')

        self.addfolderchooser = Gtk.FileChooserDialog(
            title=_('Add Folder…'),
            transient_for=self.widget,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )

        self.addfolderchooser.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.addfolderchooser.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        self.addfolderchooser.set_select_multiple(True)
        self.addfolderchooser.set_local_only(False)

        self.combo = Gtk.ComboBox()
        self.store = Gtk.ListStore(str)
        self.combo.set_model(self.store)
        combo_rend = Gtk.CellRendererText()
        self.combo.pack_start(combo_rend, True)
        self.combo.add_attribute(combo_rend, 'text', 0)

        for files in filepattern:
            self.store.append(['{} ({})'.format(files[0], files[1])])

        self.combo.set_active(0)
        self.addfolderchooser.set_extra_widget(self.combo)

        self.addchooser = Gtk.FileChooserDialog(
            title=_('Add Files…'),
            transient_for=self.widget,
            action=Gtk.FileChooserAction.OPEN
        )

        self.addchooser.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.addchooser.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        self.addchooser.set_select_multiple(True)
        self.addchooser.set_local_only(False)

        self.addfile_combo = Gtk.ComboBox()
        self.addfile_store = Gtk.ListStore(str)
        self.addfile_combo.set_model(self.addfile_store)
        combo_rend = Gtk.CellRendererText()
        self.addfile_combo.pack_start(combo_rend, True)
        self.addfile_combo.add_attribute(combo_rend, 'text', 0)
        self.addfile_combo.connect('changed', self.on_addfile_combo_changed)

        self.pattern = []
        for files in filepattern:
            self.pattern.append(files[1])
            self.addfile_store.append(['{} ({})'.format(files[0], files[1])])

        self.addfile_combo.set_active(0)
        self.addchooser.set_extra_widget(self.addfile_combo)

        # self.aboutdialog.set_property('name', NAME)
        # self.aboutdialog.set_property('version', VERSION)
        # self.aboutdialog.set_transient_for(self.widget)

        self.converter_queue = None

        self.sensitive_widgets = {}
        for name in self.sensitive_names:
            self.sensitive_widgets[name] = builder.get_object(name)
        for name in self.unsensitive_when_converting:
            self.sensitive_widgets[name] = builder.get_object(name)

        self.set_sensitive()
        self.set_status()

        # wrap the widget
        self.progressbar = ProgressBar(self.progressbar)

    # This bit of code constructs a list of methods for binding to Gtk+
    # signals. This way, we don't have to maintain a list manually,
    # saving editing effort. It's enough to add a method to the suitable
    # class and give the same name in the .glade file.

    def __getattr__(self, attribute):
        """Allow direct use of window widget."""
        widget = self.builder.get_object(attribute)
        if widget is None:
            raise AttributeError('Widget \'{}\' not found'.format(attribute))
        self.__dict__[attribute] = widget  # cache result
        return widget

    def close(self, *args):
        logger.debug('closing…')
        self.filelist.cancel()
        if self.converter_queue is not None:
            self.converter_queue.cancel()
        if self.filelist.discoverers is not None:
            self.filelist.discoverers.cancel()
        self.widget.hide()
        self.widget.destroy()
        # wait one second…
        # yes, this sucks badly, but signals can still be called by gstreamer
        # so wait a bit for things to calm down, and quit.
        # It can be optionally changed in the settings dict to speed up tests.
        gtk_sleep(settings.get('gtk_close_sleep', 1))
        Gtk.main_quit()
        return True

    on_window_delete_event = close
    on_quit_activate = close
    on_quit_button_clicked = close

    def on_add_activate(self, *args):
        last_folder = self.prefs.settings.get_string('last-used-folder')
        if last_folder:
            self.addchooser.set_current_folder_uri(last_folder)

        ret = self.addchooser.run()
        folder = self.addchooser.get_current_folder_uri()
        self.addchooser.hide()
        if ret == Gtk.ResponseType.OK and folder:
            self.filelist.add_uris(self.addchooser.get_uris())
            self.prefs.settings.set_string('last-used-folder', folder)
        self.set_sensitive()

    def addfile_filter_cb(self, info, pattern):
        filename = info.display_name
        return filename.lower().endswith(pattern[1:])

    def on_addfile_combo_changed(self, w):
        """Set a new filter for the filechooserwidget."""
        filefilter = Gtk.FileFilter()
        if self.addfile_combo.get_active():
            filefilter.add_custom(
                Gtk.FileFilterFlags.DISPLAY_NAME,
                self.addfile_filter_cb,
                self.pattern[self.addfile_combo.get_active()]
            )
        else:
            filefilter.add_pattern('*.*')
        self.addchooser.set_filter(filefilter)

    def on_addfolder_activate(self, *args):
        last_folder = self.prefs.settings.get_string('last-used-folder')
        if last_folder:
            self.addfolderchooser.set_current_folder_uri(last_folder)

        ret = self.addfolderchooser.run()
        folders = self.addfolderchooser.get_uris()
        folder = self.addfolderchooser.get_current_folder_uri()
        self.addfolderchooser.hide()
        if ret == Gtk.ResponseType.OK:
            extensions = None
            if self.combo.get_active():
                patterns = filepattern[self.combo.get_active()][1].split(';')
                extensions = [os.path.splitext(p)[1] for p in patterns]
            self.filelist.add_uris(folders, None, extensions)
            if folder:
                self.prefs.settings.set_string('last-used-folder', folder)

        self.set_sensitive()

    def on_remove_activate(self, *args):
        model, paths = self.filelist_selection.get_selected_rows()
        while paths:
            # Remove files
            childpath = model.convert_path_to_child_path(paths[0])
            i = self.filelist.model.get_iter(childpath)
            self.filelist.remove(i)
            model, paths = self.filelist_selection.get_selected_rows()
        # re-assign row numbers
        files = self.filelist.get_files()
        for i, sound_file in enumerate(files):
            sound_file.filelist_row = i
        self.set_sensitive()

    def on_clearlist_activate(self, *args):
        self.filelist.model.clear()
        self.filelist.filelist.clear()
        self.filelist.invalid_files_list = []
        self.invalid_files_button.set_visible(False)
        self.set_sensitive()
        self.set_status()

    def on_showinvalid_activate(self, *args):
        self.showinvalid_dialog_label.set_label(
            'Those are the files that could '
            'not be added to the list due to not\ncontaining audio data, '
            'being broken or being incompatible to gstreamer:'
        )
        buffer = Gtk.TextBuffer()
        buffer.set_text('\n'.join(self.filelist.invalid_files_list))
        self.showinvalid_dialog_list.set_buffer(buffer)
        self.showinvalid_dialog.run()
        self.showinvalid_dialog.hide()

    def do_convert(self):
        """Start the conversion."""
        name_generator = TargetNameGenerator()
        files = self.filelist.get_files()
        self.converter_queue = TaskQueue()
        self.converter_queue.set_on_queue_finished(self.on_queue_finished)
        for sound_file in files:
            gtk_iteration()
            self.converter_queue.add(Converter(
                sound_file,
                name_generator
            ))
        # all was OK
        self.set_status()
        self.converter_queue.run()

        # try to make the progress bars look smooth by calling this often
        self.update_progress()
        GLib.timeout_add(1000 / 20, self.update_progress)

        # since the remining time shows only seconds, there is no need to
        # call it more often than once per second
        self.update_remaining()
        GLib.timeout_add(1000, self.update_remaining)

        self.set_sensitive()

    def update_remaining(self):
        """Refresh the remaining time in the title bar and bottom left.

        Can be used in GLib.timeout_add.
        """
        paused = self.converter_queue.paused
        running = len(self.converter_queue.running) > 0

        if not running:
            # conversion done
            self.filelist.hide_row_progress()
            return False

        if not paused and running:
            converter_queue = self.converter_queue

            if converter_queue is None:
                self.progressfile.set_markup('')
                self.filelist.hide_row_progress()
                self.progressbar.set_show_text(False)
                return

            if converter_queue.paused:
                self.progressbar.set_text(_('Paused'))
                title = '{} - {}'.format(_('SoundConverter'), _('Paused'))
                self.widget.set_title(title)
                return

            # how long it has already been running
            duration = converter_queue.get_duration()
            if duration < 1:
                # wait a bit not to display crap
                self.progressbar.set_text(_('Estimating…'))
                self.progressbar.set_show_text(True)
                return

            # remainign duration
            remaining = converter_queue.get_remaining()
            if remaining is not None:
                seconds = max(remaining % 60, 1)
                minutes = remaining / 60
                remaining_str = _('%d:%02d left') % (minutes, seconds)
                self.progressbar.set_text(remaining_str)
                self.progressbar.set_show_text(True)
                title = '{} - {}'.format(_('SoundConverter'), remaining_str)
                self.widget.set_title(title)
                # -1 because the progressbar should get a chance for
                # displaying 100% and not get hidden too early
                fraction = duration / (duration + remaining - 1)
                self.progressbar.set_fraction(fraction)

        # return True to keep the GLib timeout running
        return True

    def update_progress(self):
        """Refresh all progress bars.

        Can be used in GLib.timeout_add.
        """
        paused = self.converter_queue.paused
        running = len(self.converter_queue.running) > 0

        if not running:
            # conversion done
            self.filelist.hide_row_progress()
            return False

        if not paused and running:
            # if paused, don't refresh the progress
            task_progress = self.converter_queue.get_progress()[1]
            for task, progress in task_progress:
                self.set_file_progress(task.sound_file, progress)

        # return True to keep the GLib timeout running
        return True

    def on_convert_button_clicked(self, *args):
        # reset and show progress bar
        self.progressbar.set_fraction(0)
        self.progress_frame.show()
        self.status_frame.hide()
        self.set_status(_('Converting'))
        for soundfile in self.filelist.get_files():
            self.set_file_progress(soundfile, 0.0)
        # start conversion
        self.do_convert()
        # update ui
        self.set_sensitive()

    def on_button_pause_clicked(self, *args):
        if self.converter_queue.paused:
            self.converter_queue.resume()
        else:
            self.converter_queue.pause()

    def on_button_cancel_clicked(self, *args):
        self.converter_queue.cancel()
        self.set_status(_('Canceled'))
        self.set_sensitive()
        self.conversion_ended()

    def on_select_all_activate(self, *args):
        self.filelist.widget.get_selection().select_all()

    def on_clear_activate(self, *args):
        self.filelist.widget.get_selection().unselect_all()

    def on_preferences_activate(self, *args):
        self.prefs.run()

    on_prefs_button_clicked = on_preferences_activate

    def on_about_activate(self, *args):
        about = self.aboutdialog
        about.set_property('name', NAME)
        about.set_property('version', VERSION)
        about.set_transient_for(self.widget)
        # TODO: about.set_property('translator_credits', TRANSLATORS)
        about.run()

    def on_aboutdialog_response(self, *args):
        self.aboutdialog.hide()

    def selection_changed(self, *args):
        self.set_sensitive()

    def on_queue_finished(self, queue):
        """Should be called when all conversions are completed."""
        total_time = queue.get_duration()
        msg = _('Conversion done in %s') % format_time(total_time)
        error_count = len([
            task for task in queue.done
            if task.error
        ])
        if error_count > 0:
            msg += ', {} error(s)'.format(error_count)

        logger.info(msg)

        self.conversion_ended(msg)

    def conversion_ended(self, msg=None):
        """Reset the window.

        Parameters
        ----------
        msg : string
            If set, will display this on the bottom left.
        """
        self.progress_frame.hide()
        self.filelist.hide_row_progress()
        self.status_frame.show()
        self.widget.set_sensitive(True)
        self.set_status(msg)
        try:
            from gi.repository import Unity
            name = "soundconverter.desktop"
            launcher = Unity.LauncherEntry.get_for_desktop_id(name)
            launcher.set_property("progress_visible", False)
        except ImportError:
            pass

    def set_widget_sensitive(self, name, sensitivity):
        self.sensitive_widgets[name].set_sensitive(sensitivity)

    def is_running(self):
        """Is a conversion (both paused and running) currently going on?"""
        queue = self.converter_queue
        return queue is not None and queue.running

    def set_sensitive(self):
        """Update the sensitive state of UI for the current state."""
        for widget_name in self.unsensitive_when_converting:
            self.set_widget_sensitive(widget_name, not self.is_running())

        if not self.is_running():
            self.set_widget_sensitive(
                'remove',
                self.filelist_selection.count_selected_rows() > 0
            )
            self.set_widget_sensitive(
                'convert_button',
                self.filelist.is_nonempty()
            )

    def set_file_progress(self, sound_file, progress):
        """Show the progress bar of a single file in the UI."""
        row = sound_file.filelist_row
        self.filelist.set_row_progress(row, progress)

    def set_status(self, text=None, ready=True):
        if not text:
            text = _('Ready')
        if ready:
            self.widget.set_title(_('SoundConverter'))
        self.statustext.set_markup(text)
        self.set_sensitive()
        gtk_iteration(True)

    def is_active(self):
        return self.widget.is_active()


NAME = VERSION = None
# use a global array as pointer, so that the constructed
# SoundConverterWindow can be accessed from unittests
win = [None]


def gui_main(name, version, gladefile, input_files):
    """Launch the soundconverter in GTK GUI mode.

    The values for name, version and gladefile are
    determined during `make` and provided when this
    function is called in soundconverter.py

    input_files is an array of string paths, read from
    the command line arguments. It can also be an empty
    array since the user interface provides the tools
    for adding files.
    """
    global NAME, VERSION
    NAME, VERSION = name, version
    GLib.set_application_name(name)
    GLib.set_prgname(name)

    input_files = list(map(filename_to_uri, input_files))

    builder = Gtk.Builder()
    builder.set_translation_domain(name.lower())
    builder.add_from_file(gladefile)

    window = SoundConverterWindow(builder)

    set_error_handler(ErrorDialog(builder))

    window.filelist.add_uris(input_files)
    window.set_sensitive()

    global win
    win[0] = window

    Gtk.main()
