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

from datetime import datetime
import os
import sys
import time
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango

from soundconverter.gstreamer.discoverer import add_discoverers
from soundconverter.interface.mainloop import gtk_iteration, idle
from soundconverter.interface.notify import notification
from soundconverter.util.error import show_error
from soundconverter.util.fileoperations import unquote_filename, vfs_walk
from soundconverter.util.formatting import format_time
from soundconverter.util.logger import logger
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.taskqueue import TaskQueue

# Names of columns in the file list
MODEL = [
    GObject.TYPE_STRING,  # visible filename
    GObject.TYPE_PYOBJECT,  # soundfile
    GObject.TYPE_FLOAT,  # progress
    GObject.TYPE_STRING,  # status
    GObject.TYPE_STRING,  # complete filename
]

COLUMNS = ["filename"]


class FileList:
    """List of files added by the user."""

    # List of MIME types which we accept for drops.
    drop_mime_types = ["text/uri-list", "text/plain", "STRING"]

    def __init__(self, window, builder):
        self.window = window
        self.discoverers = None
        self.filelist = set()

        self.model = Gtk.ListStore(*MODEL)
        self.progress_cache = {}

        self.widget = builder.get_object("filelist")
        self.widget.props.fixed_height_mode = True
        self.sortedmodel = Gtk.TreeModelSort(model=self.model)
        self.widget.set_model(self.sortedmodel)
        self.sortedmodel.set_sort_column_id(4, Gtk.SortType.ASCENDING)
        self.widget.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        self.widget.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        targets = [(accepted, 0, i) for i, accepted in enumerate(self.drop_mime_types)]
        self.widget.drag_dest_set_target_list(targets)

        self.widget.connect("drag-data-received", self.drag_data_received)

        renderer = Gtk.CellRendererProgress()
        column = Gtk.TreeViewColumn(
            "progress",
            renderer,
            value=2,
            text=3,
        )
        column.props.sizing = Gtk.TreeViewColumnSizing.FIXED
        self.widget.append_column(column)
        self.progress_column = column
        self.progress_column.set_visible(False)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        column = Gtk.TreeViewColumn(
            "Filename",
            renderer,
            markup=0,
        )
        column.props.sizing = Gtk.TreeViewColumnSizing.FIXED
        column.set_expand(True)
        self.widget.append_column(column)

        self.window.progressbarstatus.hide()

        self.invalid_files_list = []
        self.good_uris = []

    def drag_data_received(self, widget, context, x, y, selection, mime_id, time):
        widget.stop_emission("drag-data-received")
        if 0 <= mime_id < len(self.drop_mime_types):
            text = selection.get_data().decode("utf-8")
            uris = [uri.strip() for uri in text.split("\n")]
            self.add_uris(uris)
            context.finish(True, False, time)

    def get_files(self):
        """Return all valid SoundFile objects."""
        return [i[1] for i in self.sortedmodel]

    @idle
    def add_uris(self, uris, base=None, extensions=None):
        """Add URIs that should be converted to the list in the GTK interface.

        uris is a list of string URIs, which are absolute paths
        starting with 'file://'

        extensions is a list of strings like ['.ogg', '.oga'],
        in which case only files of this type are added to the
        list. This can be useful when files of multiple types
        are inside a directory and only some of them should be
        converted. Default:None which accepts all types.
        """
        self.progress_cache = {}

        if len(uris) == 0:
            return

        start_t = time.time()
        files = []
        self.window.set_status(_("Scanning files…"))
        # for whichever reason, that set_status needs some more iterations
        # to show up:
        gtk_iteration(True)
        self.window.progressbarstatus.show()
        self.window.progressbarstatus.set_fraction(0)

        for uri in uris:
            gtk_iteration()
            if not uri:
                continue
            if uri.startswith("cdda:"):
                show_error(
                    "Cannot read from Audio CD.",
                    "Use SoundJuicer Audio CD Extractor instead.",
                )
                return
            info = Gio.file_parse_name(uri).query_file_type(
                Gio.FileMonitorFlags.NONE,
                None,
            )
            if info == Gio.FileType.DIRECTORY:
                logger.info(f"walking: '{uri}'")
                if len(uris) == 1:
                    # if only one folder is passed to the function,
                    # use its parent as base path.
                    base = os.path.dirname(uri)

                # get a list of all the files as URIs in
                # that directory and its subdirectories
                start = datetime.now()
                filelist = vfs_walk(uri)
                stop = datetime.now()
                duration = stop - start
                logger.info(f"Discovered {len(filelist)} files in {duration}")
                sys.exit(0)
                accepted = []
                if extensions:
                    for filename in filelist:
                        for extension in extensions:
                            if filename.lower().endswith(extension):
                                accepted.append(filename)
                    filelist = accepted
                files.extend(filelist)
            else:
                files.append(uri)

        files = [f for f in files if not f.endswith("~SC~")]

        if len(files) == 0:
            show_error("No files found!", "")

        if not base:
            base = os.path.commonprefix(files)
            if base and not base.endswith("/"):
                # we want a common folder
                base = base[0 : base.rfind("/")]
                base += "/"
        else:
            base += "/"

        scan_t = time.time()
        logger.info("analysing file integrity")

        # self.good_uris will be populated
        # by the discoverer.
        # It is a list of uris and only contains those files
        # that can be handled by gstreamer
        self.good_uris = []

        self.discoverers = TaskQueue()
        sound_files = []
        for filename in files:
            sound_file = SoundFile(filename, base)
            sound_files.append(sound_file)

        add_discoverers(self.discoverers, sound_files)

        self.discoverers.connect("done", self.discoverer_queue_ended)
        self.discoverers.run()

        self.window.set_status("{}".format(_("Adding Files…")))
        logger.info(f"adding: {len(files)} files")

        # show progress and enable GTK main loop iterations
        # so that the ui stays responsive
        self.window.progressbarstatus.set_text(f"0/{len(files)}")
        self.window.progressbarstatus.set_show_text(True)

        while self.discoverers.running:
            progress = self.discoverers.get_progress()[0]
            if progress:
                completed = int(progress * len(files))
                self.window.progressbarstatus.set_fraction(progress)
                self.window.progressbarstatus.set_text(
                    f"{completed}/{len(files)}",
                )
            gtk_iteration()
        logger.info(
            f"Discovered {len(files)} audiofiles in {round(self.discoverers.get_duration(), 1)} s",
        )

        self.window.progressbarstatus.set_show_text(False)

        # see if one of the files with an audio extension
        # was not readable.
        known_audio_types = [
            ".flac",
            ".mp3",
            ".aac",
            ".m4a",
            ".mpeg",
            ".opus",
            ".vorbis",
            ".ogg",
            ".wav",
        ]

        # invalid_files is the number of files that are not
        # added to the list in the current function call
        invalid_files = 0
        # out of those files, that many have an audio file extension
        broken_audiofiles = 0

        sound_files = []
        for discoverer in self.discoverers.all_tasks:
            sound_files += discoverer.sound_files

        for sound_file in sound_files:
            # create a list of human readable file paths
            # that were not added to the list
            if not sound_file.readable:
                filename = sound_file.filename

                extension = os.path.splitext(filename)[1].lower()
                if extension in known_audio_types:
                    broken_audiofiles += 1

                subfolders = sound_file.subfolders
                relative_path = os.path.join(subfolders, filename)

                self.invalid_files_list.append(relative_path)
                invalid_files += 1
                continue
            if sound_file.uri in self.filelist:
                logger.info(f"file already present: '{sound_file.uri}'")
                continue
            self.append_file(sound_file)

        if invalid_files > 0:
            self.window.invalid_files_button.set_visible(True)
            if len(files) == invalid_files == 1:
                # case 1: the single file that should be added is not supported
                show_error(
                    _("The specified file is not supported!"),
                    _("Either because it is broken or not an audio file."),
                )

            elif len(files) == invalid_files:
                # case 2: all files that should be added cannot be added
                show_error(
                    _("All {} specified files are not supported!").format(len(files)),
                    _("Either because they are broken or not audio files."),
                )

            else:
                # case 3: some files could not be added (that can already be
                # because there is a single picture in a folder of hundreds
                # of sound files). Show an error if this skipped file has a
                # soundfile extension, otherwise don't bother the user.
                logger.info(
                    f"{invalid_files} of {len(files)} files were not added to the list",
                )
                if broken_audiofiles > 0:
                    show_error(
                        ngettext(
                            "One audio file could not be read by GStreamer!",
                            "{} audio files could not be read by GStreamer!",
                            broken_audiofiles,
                        ).format(broken_audiofiles),
                        _('Check "Invalid Files" in the menu for more information.'),
                    )
        else:
            # case 4: all files were successfully added. No error message
            pass

        self.window.set_status()
        self.window.progressbarstatus.hide()
        end_t = time.time()
        logger.debug(
            f"Added {len(files)} files in {end_t - start_t:.2f}s (scan {scan_t - start_t:.2f}s, add {end_t - scan_t:.2f}s)",
        )

    def discoverer_queue_ended(self, queue):
        # all tasks done
        self.window.set_sensitive()
        self.window.conversion_ended()

        total_time = queue.get_duration()
        msg = _("Tasks done in %s") % format_time(total_time)

        errors = [task.error for task in queue.done if task.error is not None]
        if len(errors) > 0:
            msg += f", {len(errors)} error(s)"

        self.window.set_status(msg)
        if not self.window.is_active():
            notification(msg)

        readable = []
        for discoverer in self.discoverers.all_tasks:
            for sound_file in discoverer.sound_files:
                if sound_file.readable:
                    readable.append(sound_file)

        self.good_uris = [sound_file.uri for sound_file in readable]
        self.window.set_status()
        self.window.progressbarstatus.hide()

    def cancel(self):
        if self.discoverers is not None:
            self.discoverers.cancel()

    def format_cell(self, sound_file):
        """Take a SoundFile and return a human readable path to it."""
        return GLib.markup_escape_text(unquote_filename(sound_file.filename))

    def set_row_progress(self, number, progress):
        """Update the progress bar of a single row/file."""
        # when convertin a lot of files updating all progress bars really becomes
        # quite an expensive task
        cached = self.progress_cache.get(number, 0)
        # - progress_cache is faster than self.model for this optimization
        # - skip small changes
        # - make sure it will be set to 1 even if the change is small
        if (progress == 1 and cached != 1) or abs(cached - progress) > 0.02:
            self.model[number][2] = progress * 100.0
            self.progress_cache[number] = progress
            return

    def hide_row_progress(self):
        self.progress_column.set_visible(False)

    def show_row_progress(self):
        self.progress_column.set_visible(True)

    def append_file(self, sound_file):
        """Add a valid SoundFile object to the list of files in the GUI.

        Parameters
        ----------
        sound_file : SoundFile
            This soundfile is expected to be readable by gstreamer
        """
        self.model.append(
            [self.format_cell(sound_file), sound_file, 0.0, "", sound_file.uri],
        )
        self.filelist.add(sound_file.uri)
        sound_file.filelist_row = len(self.model) - 1

    def remove(self, iterator):
        uri = self.model.get(iterator, 1)[0].uri
        self.filelist.remove(uri)
        self.model.remove(iterator)

    def is_nonempty(self):
        try:
            self.model.get_iter((0,))
        except ValueError:
            return False
        return True
