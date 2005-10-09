#!/usr/bin/python
#
# SoundConverter - GNOME application for converting between audio formats. 
# Copyright 2004 Lars Wirzenius
# Copyright 2005 Gautier Portet
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
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

NAME = "SoundConverter"
VERSION = "0.8.0"
GLADE = "soundconverter.glade"

# GNOME and related stuff.
import pygtk
pygtk.require("2.0")
import gtk
import gtk.glade
import gnome
import gnome.ui
import gst
import gconf
import gobject
import urllib

import time

try:
    # gnome.vfs is deprecated
    import gnomevfs
except ImportError:
    import gnome.vfs
    gnomevfs = gnome.vfs

# This is missing from gst, for some reason.
FORMAT_PERCENT_SCALE = 10000

# Python standard stuff.
import sys
import os
import inspect
import getopt
import textwrap
import urllib
import urlparse
import string

#localization
import locale
import gettext
PACKAGE = "soundconverter"
gettext.bindtextdomain(PACKAGE,'/usr/share/locale')
locale.setlocale(locale.LC_ALL,'')
gettext.textdomain(PACKAGE)
gettext.install(PACKAGE,localedir=None,unicode=1)

gtk.glade.bindtextdomain(PACKAGE,'/usr/share/locale')
gtk.glade.textdomain(PACKAGE)

TRANSLATORS = _("Guillaume Bedot <littletux@zarb.org>")

# Names of columns in the file list
#VISIBLE_COLUMNS = [_("Artist"), _("Album"), _("Title"), "filename"]
VISIBLE_COLUMNS = [_("Artist"), _("Album"), _("Title")]
ALL_COLUMNS = VISIBLE_COLUMNS + ["META"] 

MP3_CBR, MP3_ABR, MP3_VBR = range(3)


class SoundConverterException(Exception):

    def __init__(self, primary, secondary):
        Exception.__init__(self)
        self.primary = primary
        self.secondary = secondary
        

def filename_to_uri(filename):
    return "file://" + urllib.quote(os.path.abspath(filename))


class SoundFile:

    """Meta data information about a sound file (uri, tags)."""

    def __init__(self, uri):
        self.uri = uri
        self.tags = {}
        
    def get_uri(self):
        return self.uri
        
    def add_tags(self, taglist):
        for key in taglist.keys():
            self.tags[key] = taglist[key]
            
    def get_tag_names(self):
        return self.tags.key()
            
    def get_tag(self, key, default=""):
        return self.tags.get(key, default)

    get = get_tag
    __getitem__ = get_tag

    def keys(self):
        return self.tags.keys()


class TargetNameCreationFailure(SoundConverterException):

    """Exception thrown when TargetNameGenerator can't create name."""

    def __init__(self, name):
        SoundConverterException.__init__(self, _("File exists."),
                                         _("The file %s exists already"))

class TargetNameGenerator:

    """Generator for creating the target name from an input name."""

    nice_chars = string.ascii_letters + string.digits + ".-_/"

    def __init__(self):
        self.folder = None
        self.subfolders = ""
        self.basename= "%(.inputname)s"
        self.suffix = None
        self.replace_messy_chars = False
        self.max_tries = 2
        self.exists = os.path.exists

    # This is useful for unit testing.        
    def set_exists(self, exists):
        self.exists = exists

    def set_target_suffix(self, suffix):
        self.suffix = suffix
        
    def set_folder(self, folder):
        self.folder = folder
        
    def set_subfolder_pattern(self, pattern):
        self.subfolders = pattern
        
    def set_basename_pattern(self, pattern):
        self.basename = pattern
        
    def set_replace_messy_chars(self, yes_or_no):
        self.replace_messy_chars = yes_or_no
        
    def get_target_name(self, sound_file):
        u = gnomevfs.URI(sound_file.get_uri())
        root, ext = os.path.splitext(u.path)
        if u.host_port:
            host = "%s:%s" % (u.host_name, u.host_port)
        else:
            host = u.host_name

        basename = os.path.basename(root)
        root = os.path.dirname(root)

        dict = {
            ".inputname": basename,
            "album": "",
            "artist": "",
            "title": "",
            "track-number": 0,
        }
        for key in sound_file.keys():
            dict[key] = sound_file[key]

        pattern = os.path.join(self.subfolders, self.basename + self.suffix)
        result = pattern % dict
        if self.replace_messy_chars:
            s = ""
            result = urllib.unquote(result)
            for c in result:
                if c not in self.nice_chars:
                    s += "_"
                else:
                    s += c
            result = urllib.quote(s)

        if self.folder is None:
            folder = root
        else:
            folder = self.folder
        result = os.path.join(folder, result)

        tuple = (u.scheme, host, result, "", u.fragment_identifier)
        u2 = urlparse.urlunsplit(tuple)
        if self.exists(u2):
            raise TargetNameCreationFailure(u2)
        return u2


class ErrorDialog:

    def __init__(self, glade):
        self.dialog = glade.get_widget("error_dialog")
        self.primary = glade.get_widget("primary_error_label")
        self.secondary = glade.get_widget("secondary_error_label")
        
    def show(self, primary, secondary):
        self.primary.set_markup(primary)
        self.secondary.set_markup(secondary)
        self.dialog.run()
        self.dialog.hide()

    def encode(self, str):
        str = "&amp;".join(str.split("&"))
        str = "&lt;".join(str.split("<"))
        str = "&gt;".join(str.split(">"))
        return str

    def show_exception(self, exception):
        self.show("<b>%s</b>" % self.encode(exception.primary),
                  exception.secondary)


class ErrorPrinter:

    def show(self, primary, secondary):
        sys.stderr.write(_("\n\nError: %s\n%s\n") % (primary, secondary))
        sys.exit(1)

    def show_exception(self, e):
        self.show(e.primary, e.secondary)


error = None



class BackgroundTask:

    """A background task.
    
    To use: derive a subclass and define the methods setup, work, and
    finish. Then call the run method when you want to start the task.
    Call the stop method if you want to stop the task before it finishes
    normally."""

    def run(self):
        """Start running the task. Call setup()."""
        try:
            self.setup()
        except SoundConverterException, e:
            error.show_exception(e)
            return
        self.id = gobject.idle_add(self.do_work)
        self.run_start_times = os.times()
    
    def do_work(self):
        """Do some work by calling work(). Call finish() if work is done."""
        try:
            if self.work():
                return True
            else:
                self.run_finish_times = os.times()
                self.finish()
                return False
        except SoundConverterException, e:
            error.show_exception(e)
            return False

    def stop(self):
        """Stop task processing. Finish() is not called."""
        if 'id' in dir(self) and self.id is not None:
            gobject.source_remove(self.id)
            self.id = None

    def setup(self):
        """Set up the task so it can start running."""
        pass
        
    def work(self):
        """Do some work. Return False if done, True if more work to do."""
        return False
        
    def finish(self):
        """Clean up the task after all work has been done."""
        pass


class TaskQueue(BackgroundTask):

    """A queue of tasks.
    
    A task queue is a queue of other tasks. If you need, for example, to
    do simple tasks A, B, and C, you can create a TaskQueue and add the
    simple tasks to it:
    
        q = TaskQueue()
        q.add(A)
        q.add(B)
        q.add(C)
        q.run()
        
    The task queue behaves as a single task. It will execute the
    tasks in order and start the next one when the previous finishes."""

    def __init__(self):
        self.tasks = []
        self.running = False
        
    def is_running(self):
        return self.running

    def add(self, task):
        self.tasks.append(task)
        
    def get_current_task(self):
        if self.tasks:
            return self.tasks[0]
        else:
            return None

    def setup(self):
        self.running = True
        if self.tasks:
            self.tasks[0].setup()
            self.setup_hook(self.tasks[0])
            
    def work(self):
        if self.tasks:
            ret = self.tasks[0].work()
            self.work_hook(self.tasks[0])
            if not ret:
                self.tasks[0].finish()
                self.finish_hook(self.tasks[0])
                self.tasks = self.tasks[1:]
                if self.tasks:
                    self.tasks[0].setup()
        return len(self.tasks) > 0

    def finish(self):
        self.running = False

    def stop(self):
        if self.tasks:
            self.tasks[0].stop()
        BackgroundTask.stop(self)
        self.running = False
        self.tasks = []

    # The following hooks are called after each sub-task has been set up,
    # after its work method has been called, and after it has finished.
    # Subclasses may override these to provide additional processing.

    def setup_hook(self, task):
        pass
        
    def work_hook(self, task):
        pass
        
    def finish_hook(self, task):
        pass


class NoLink(SoundConverterException):
    
    def __init__(self):
        SoundConverterException.__init__(self, _("Internal error"),
                                _("Couldn't link GStreamer elements.\n Please report this as a bug."))

class UnknownType(SoundConverterException):
    
    def __init__(self, uri, mime_type):
        SoundConverterException.__init__(self, _("Unknown type %s") % mime_type,
                                (_("The file %s is of an unknown type.\n Please ask the developers to add support\n for files of this type if it is important\n to you.")) % uri)


class Pipeline(BackgroundTask):

    """A background task for running a GstPipeline."""

    def __init__(self):
        self.pipeline = gst.Pipeline()
        
    def setup(self):
        self.play()
        
    def work(self):
        if self.pipeline.get_state() == gst.STATE_NULL:
            return False
        return self.pipeline.iterate()

    def finish(self):
        self.stop_pipeline()

    def make_element(self, elementkind, elementname):
        factory = gst.element_factory_find(elementkind)
        if factory:
            return factory.create(elementname)
        else:
            return None
    
    def add(self, element):
        assert self.pipeline.get_state() != gst.STATE_PLAYING
        elements = self.pipeline.get_list()
        self.pipeline.add(element)
        if elements and not elements[-1].link(element):
            raise NoLink()

    def pause(self):
        self.pipeline.set_state(gst.STATE_PAUSED)

    def play(self):
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop_pipeline(self):
        self.pipeline.set_state(gst.STATE_NULL)

    def get_progress(self):
        elements = self.pipeline.get_list()
        value = elements[0].query(gst.QUERY_POSITION, gst.FORMAT_PERCENT)
        return float(value) / float(FORMAT_PERCENT_SCALE)

    def get_bytes_progress(self):
        elements = self.pipeline.get_list()
        return elements[0].query(gst.QUERY_POSITION, gst.FORMAT_BYTES)


class Decoder(Pipeline):

    """A GstPipeline background task that decodes data and finds tags."""

    def __init__(self, sound_file):
        Pipeline.__init__(self)
        self.sound_file = sound_file
        
        filesrc = self.make_element("gnomevfssrc", "src")
        filesrc.set_property("location", self.sound_file.get_uri())
        self.add(filesrc)

        decodebin = self.make_element("decodebin", "decodebin")
        decodebin.connect("found-tag", self.found_tag)
        decodebin.connect("new-decoded-pad", self.new_decoded_pad)
        self.add(decodebin)

    def found_tag(self, decoder, something, taglist):
        pass

    def new_decoded_pad(self, decoder, pad, is_last):
        pass

    def get_sound_file(self):
        return self.sound_file

    def get_input_uri(self):
        return self.sound_file.get_uri()

    def get_size_in_bytes(self):
        # gst.QUERY_SIZE doesn't work reliably until we have ran the
        # pipeline for a while. Thus we look at the size in a different
        # way.
        uri = self.get_input_uri()
        try:
            info = gnomevfs.get_file_info(uri)
            return info.size
        except gnomevfs.NotFoundError:
            return 0

class TagReader(Decoder):

    """A GstPipeline background task for finding meta tags in a file."""

    def __init__(self, sound_file):
        Decoder.__init__(self, sound_file)
        self.found_tag_hook = None
        self.found_tags = False

    def set_found_tag_hook(self, found_tag_hook):
        self.found_tag_hook = found_tag_hook


    def found_tag(self, decoder, something, taglist):
        self.sound_file.add_tags(taglist)

        # tags from ogg vorbis files comes with two callbacks,
        # the first callback containing just the stream serial number.
        # The second callback contains the tags we're interested in.
        if not taglist.has_key('serial'):
            self.found_tags = True

    def work(self):
        return Decoder.work(self) and not self.found_tags

    def finish(self):
        Decoder.finish(self)
        if self.found_tag_hook:
            self.found_tag_hook(self)


class ConversionTargetExists(SoundConverterException):

    def __init__(self, uri):
        SoundConverterException.__init__(self, _("Target exists."),
                                         (_("The output file %s already exists.")) % uri)


class Converter(Decoder):

    """A background task for converting files to another format."""

    def __init__(self, sound_file, output_filename, output_type):
        Decoder.__init__(self, sound_file)

        self.output_filename = output_filename
        self.output_type = output_type
        self.vorbis_quality = None
        self.mp3_bitrate = None
        self.mp3_mode = None
        self.mp3_quality = None
        self.added_pad_already = False

        self.encoders = {
            "audio/x-vorbis": self.add_oggvorbis_encoder,
            "audio/x-flac": self.add_flac_encoder,
            "audio/x-wav": self.add_wav_encoder,
            "audio/mpeg": self.add_mp3_encoder,
        }

    def new_decoded_pad(self, decoder, pad, is_last):
        if self.added_pad_already:
            return
        if not pad.get_caps():
            return
        if "audio" not in pad.get_caps()[0].get_name():
            return

        self.pause()
        
        audioconverter = self.make_element("audioconvert", "audioconverter")
        self.pipeline.add(audioconverter)
        pad.link(audioconverter.get_pad("sink"))
        
        encoder = self.encoders[self.output_type]()
        if not encoder:
            # TODO: add proper error management when an encoder cannot be created
            dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR,
                        gtk.BUTTONS_OK, " Cannot create a decoder for '%s' format." % \
                        self.output_type )
            dialog.run()
            dialog.hide()
            return
        self.add(encoder)
        print "using encoder: %s (%s)" % \
            (encoder.get_factory().get_name(), encoder.get_factory().get_longname())
        
        tuple = urlparse.urlparse(self.output_filename)
        path = tuple[2]
        dirname = urllib.unquote( os.path.dirname(path) )
        if dirname and not os.path.exists(dirname):
            print "Creating Folders: '%s'" % dirname
            os.makedirs(dirname)
        #elif os.path.exists(path):
        #    raise ConversionTargetExists(self.output_filename)

        sink = self.make_element("gnomevfssink", "sink")
        print "Writing to: '%s'" % self.output_filename
        sink.set_property("location", self.output_filename)
        self.add(sink)
        
        self.play()
        self.added_pad_already = True

    def set_vorbis_quality(self, quality):
        self.vorbis_quality = quality

    def set_mp3_mode(self, mode):
        self.mp3_mode = mode

    def set_mp3_quality(self, quality):
        self.mp3_quality = quality

    def add_flac_encoder(self):
        return self.make_element("flacenc", "encoder")

    def add_wav_encoder(self):
        return self.make_element("wavenc", "encoder")

    def add_oggvorbis_encoder(self):
        vorbisenc = self.make_element("vorbisenc", "encoder")
        if self.vorbis_quality is not None:
            vorbisenc.set_property("quality", self.vorbis_quality)
            #print("setting vorbis quality: %f" % self.vorbis_quality)
            
        return vorbisenc

    def add_mp3_encoder(self):
    
        mp3enc = self.make_element("lame", "encoder")

        # raise algorithm quality
        mp3enc.set_property("quality",2)
        
        if self.mp3_mode is not None:
            properties = {
                "cbr" : (0,"bitrate"),
                "abr" : (3,"vbr-mean-bitrate"),
                "vbr" : (4,"vbr-quality")
            }

            mp3enc.set_property("vbr", properties[self.mp3_mode][0])
            mp3enc.set_property(properties[self.mp3_mode][1], self.mp3_quality)
        
        return mp3enc

class FileList:

    """List of files added by the user."""

    # List of MIME types which we accept for drops.
    drop_mime_types = ["text/uri-list"]

    def __init__(self, window, glade):
        self.window = window
        self.tagreaders = TaskQueue()
        
        args = []
        for name in ALL_COLUMNS:
            if name in VISIBLE_COLUMNS:
                args.append(gobject.TYPE_STRING)
            else:
                args.append(gobject.TYPE_PYOBJECT)
        self.model = apply(gtk.ListStore, args)

        self.widget = glade.get_widget("filelist")
        self.widget.set_model(self.model)
        self.widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        
        self.widget.drag_dest_set(gtk.DEST_DEFAULT_ALL, 
                                  map(lambda i: 
                                        (self.drop_mime_types[i], 0, i), 
                                      range(len(self.drop_mime_types))),
                                  gtk.gdk.ACTION_COPY)
        self.widget.connect("drag_data_received", self.drag_data_received)

        renderer = gtk.CellRendererText()
        for name in VISIBLE_COLUMNS:
            column = gtk.TreeViewColumn(name,
                                        renderer, 
                                        text=ALL_COLUMNS.index(name))
            self.widget.append_column(column)
    
    def drag_data_received(self, widget, context, x, y, selection, 
                           mime_id, time):
        if mime_id >= 0 and mime_id < len(self.drop_mime_types):
            mime_type = self.drop_mime_types[mime_id]
            if mime_type == "text/uri-list":
                for uri in selection.data.split("\n"):
                    uri = uri.strip()
                    if uri:
                        self.add_file(SoundFile(uri))
                context.finish(True, False, time)

    def get_files(self):
        files = []
        iter = self.model.get_iter_first()
        while iter:
            file = {}
            for c in ALL_COLUMNS:
                file[c] = self.model.get_value(iter, ALL_COLUMNS.index(c))
            files.append(file)
            iter = self.model.iter_next(iter)
        return files
    
    def add_file(self, sound_file):
        tagreader = TagReader(sound_file)
        tagreader.set_found_tag_hook(self.append_file)

        self.tagreaders.add(tagreader)
        if not self.tagreaders.is_running():
            self.tagreaders.run()
            
    def append_file(self, tagreader):
        sound_file = tagreader.get_sound_file()

        fields = {}
        for key in ALL_COLUMNS:
            fields[key] = _("unknown")
        fields["META"] = sound_file
        #fields["filename"] = sound_file.get_uri()

        for field, tagname in [(_("Title"), "title"), (_("Artist"), "artist"),
                               (_("Album"), "album")]:
            fields[field] = sound_file.get_tag(tagname, fields[field])

        iter = self.model.append()
        for i in range(len(ALL_COLUMNS)):
            self.model.set(iter, i, fields[ALL_COLUMNS[i]])
            
        self.window.set_sensitive()

    def remove(self, iter):
        self.model.remove(iter)
        
    def is_nonempty(self):
        try:
            iter = self.model.get_iter((0,))
        except ValueError:
            return False
        return True


class PreferencesDialog:

    root = "/apps/SoundConverter"
    
    basename_patterns = [
        ("%(.inputname)s", _("Same as input, but with new suffix")),
        ("%(track-number)02d-%(title)s", _("Track number - title")),
        ("%(title)s", _("Track title")),
        ("%(artist)s-%(title)s", _("Artist - title")),
    ]
    
    subfolder_patterns = [
        ("%(artist)s/%(album)s", _("artist/album")),
        ("%(artist)s-%(album)s", _("artist-album")),
    ]
    
    defaults = {
        "same-folder-as-input": 1,
        "selected-folder": os.path.expanduser("~"),
        "create-subfolders": 0,
        "subfolder-pattern-index": 0,
        "name-pattern-index": 0,
        "replace-messy-chars": 0,
        "output-mime-type": "audio/x-vorbis",
        "output-suffix": ".ogg",
        "vorbis-quality": 0.6,
        "mp3-mode": "vbr",          # 0: cbr, 1: abr, 2: vbr
        "mp3-cbr-quality": 192,
        "mp3-abr-quality": 192,
        "mp3-vbr-quality": 3,
    }

    sensitive_names = ["vorbis_quality", "choose_folder", "create_subfolders",
                       "subfolder_pattern"]

    def __init__(self, glade):
        self.gconf = gconf.client_get_default()
        self.gconf.add_dir(self.root, gconf.CLIENT_PRELOAD_ONELEVEL)
        self.dialog = glade.get_widget("prefsdialog")
        self.into_selected_folder = glade.get_widget("into_selected_folder")
        self.target_folder_chooser = glade.get_widget("target_folder_chooser")
        self.example = glade.get_widget("example_filename")
        self.aprox_bitrate = glade.get_widget("aprox_bitrate")
        self.quality_tabs = glade.get_widget("quality_tabs")

        self.target_bitrate = None

        self.convert_setting_from_old_version()
        self.set_widget_initial_values(glade)
        
        self.sensitive_widgets = {}
        for name in self.sensitive_names:
            self.sensitive_widgets[name] = glade.get_widget(name)
            assert self.sensitive_widgets[name] != None
        self.set_sensitive()


    def convert_setting_from_old_version(self):
        """ try to convert previous settings"""
        
        # TODO: why not just reseting the settings if we cannot load them ?
            
        # vorbis quality was stored as an int enum
        try:
            self.get_float("vorbis-quality")
        except gobject.GError:
            print "converting old vorbis setting..."
            old_quality = self.get_int("vorbis-quality")
            self.gconf.unset(self.path("vorbis-quality"))
            quality_setting = (0,0.2,0.3,0.6,0.8)
            self.set_float("vorbis-quality", quality_setting[old_quality])
            
        # mp3 quality was stored as an int enum
        cbr = self.get_int("mp3-cbr-quality")
        if cbr <= 4:
            print "converting old mp3 quality setting...", cbr

            abr = self.get_int("mp3-abr-quality")
            vbr = self.get_int("mp3-vbr-quality")

            cbr_quality = (64, 96, 128, 192, 256)
            vbr_quality = (9, 7, 5, 3, 1)

            self.set_int("mp3-cbr-quality", cbr_quality[cbr])
            self.set_int("mp3-abr-quality", cbr_quality[abr])
            self.set_int("mp3-vbr-quality", vbr_quality[vbr])

        # mp3 mode was stored as an int enum
        try:
            self.get_string("mp3-mode")
        except gobject.GError:
            print "converting old mp3 mode setting..."
            old_mode = self.get_int("mp3-mode")
            self.gconf.unset(self.path("mp3-mode"))
            modes = ("cbr","abr","vbr")
            self.set_string("mp3-mode", modes[old_mode])

        self.gconf.clear_cache()

    def set_widget_initial_values(self, glade):
        
        self.quality_tabs.set_show_tabs(False)
        
        if self.get_int("same-folder-as-input"):
            w = glade.get_widget("same_folder_as_input")
        else:
            w = glade.get_widget("into_selected_folder")
        w.set_active(True)
        
        self.target_folder_chooser.set_filename(
            self.get_string("selected-folder"))
        self.update_selected_folder()
    
        w = glade.get_widget("create_subfolders")
        w.set_active(self.get_int("create-subfolders"))
        
        w = glade.get_widget("subfolder_pattern")
        model = w.get_model()
        model.clear()
        for pattern, desc in self.subfolder_patterns:
            iter = model.append()
            model.set(iter, 0, desc)
        w.set_active(self.get_int("subfolder-pattern-index"))

        if self.get_int("replace-messy-chars"):
            w = glade.get_widget("replace_messy_chars")
            w.set_active(True)

        mime_type = self.get_string("output-mime-type")

        # desactivate mp3 output if encoder plugin is not present
        if not gst.element_factory_find("lame"):
            print "LAME GStreamer plugin not found, desactivating MP3 output."
            w = glade.get_widget("output_mime_type_mp3")
            w.set_sensitive(False)
            mime_type = self.defaults["output-mime-type"]
            
        
        widget_name = {
                        "audio/x-vorbis": "output_mime_type_ogg_vorbis",
                        "audio/x-flac": "output_mime_type_flac",
                        "audio/x-wav": "output_mime_type_wav",
                        "audio/mpeg": "output_mime_type_mp3",
                      }.get(mime_type, None)
        if widget_name:
            w = glade.get_widget(widget_name)
            w.set_active(True)
            self.change_mime_type(mime_type)
            
        w = glade.get_widget("vorbis_quality")
        quality = self.get_float("vorbis-quality")
        quality_setting = {0:0 ,0.2:1 ,0.4:2 ,0.6:3 , 0.8:4}
        for k, v in quality_setting.iteritems():
            if abs(quality-k) < 0.01:
                w.set_active(v)
            
        self.mp3_quality = glade.get_widget("mp3_quality")
        self.mp3_mode = glade.get_widget("mp3_mode")
        #w = glade.get_widget("mp3_mode")
        #mode = self.get_int("mp3-mode")
        #w.set_active(mode)
        #self.change_mp3_mode(mode)

        mode = self.get_string("mp3-mode")
        self.change_mp3_mode(mode)


        w = glade.get_widget("basename_pattern")
        model = w.get_model()
        model.clear()
        for pattern, desc in self.basename_patterns:
            iter = model.append()
            model.set(iter, 0, desc)
        w.set_active(self.get_int("name-pattern-index"))

        self.update_example()

    def update_selected_folder(self):
        self.into_selected_folder.set_label(_("Into folder %s") % 
                                        self.get_string("selected-folder"))


    def get_bitrate_from_settings(self):
        bitrate = 0
        aprox = True
        mode = self.get_string("mp3-mode")

        mime_type = self.get_string("output-mime-type")
        
        if mime_type == "audio/x-vorbis":
            quality = self.get_float("vorbis-quality")*10
            quality = int(quality)
            bitrates = (64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 500)
            bitrate = bitrates[quality]
            
        elif mime_type == "audio/mpeg":
            quality = {
                "cbr": "mp3-cbr-quality",
                "abr": "mp3-abr-quality",
                "vbr": "mp3-vbr-quality"
            }
            bitrate = self.get_int(quality[mode])
            if mode == "vbr":
                # hum, not really, but who cares? :)
                bitrates = (320, 256, 224, 192, 160, 128, 112, 96, 80, 64)
                bitrate = bitrates[bitrate]
            if mode == "cbr":
                aprox = False

        #print "bitrate: ", bitrate

        if bitrate:
            if aprox:
                return "~%d kbps" % bitrate
            else:
                return "%d kbps" % bitrate
        else:
            return "N/A"


    def update_example(self):
        sound_file = SoundFile(os.path.expanduser("~/foo/bar.flac"))
        sound_file.add_tags({
            "artist": "Foo Bar", 
            "title": "Hi Ho", 
            "album": "IS: TOO",
            "track-number": 1L,
            "track-count": 11L,
        })
        self.example.set_text(self.generate_filename(sound_file))
        
        # UNUSED bitrate = self.get_bitrate_from_settings()
        markup = _("<small>Target bitrate: %s</small>") % self.get_bitrate_from_settings()
        self.aprox_bitrate.set_markup( markup )

    def generate_filename(self, sound_file):
        self.gconf.clear_cache()
        output_type = self.get_string("output-mime-type")
        output_suffix = {
                        "audio/x-vorbis": ".ogg",
                        "audio/x-flac": ".flac",
                        "audio/x-wav": ".wav",
                        "audio/mpeg": ".mp3",
                    }.get(output_type, None)

        generator = TargetNameGenerator()
        generator.set_target_suffix(output_suffix)
        if self.get_int("same-folder-as-input"):
            tuple = urlparse.urlparse(sound_file.get_uri())
            path = tuple[2]
            generator.set_folder(os.path.dirname(path))
        else:
            generator.set_folder(self.get_string("selected-folder"))
            if self.get_int("create-subfolders"):
                generator.set_subfolder_pattern(
                    self.get_subfolder_pattern())
        generator.set_basename_pattern(self.get_basename_pattern())
        generator.set_replace_messy_chars(
            self.get_int("replace-messy-chars"))
        
        return generator.get_target_name(sound_file)

    def set_sensitive(self):
    
        return
    
        for widget in self.sensitive_widgets.values():
            widget.set_sensitive(False)
        
        x = self.get_int("same-folder-as-input")
        for name in ["choose_folder", "create_subfolders", 
                     "subfolder_pattern"]:
            self.sensitive_widgets[name].set_sensitive(not x)
        
        self.sensitive_widgets["vorbis_quality"].set_sensitive(
            self.get_string("output-mime-type") == "audio/x-vorbis")

    def path(self, key):
        assert self.defaults.has_key(key)
        return "%s/%s" % (self.root, key)

    def get_with_default(self, getter, key):
        if self.gconf.get(self.path(key)) is None:
            return self.defaults[key]
        else:
            return getter(self.path(key))

    def get_int(self, key):
        return self.get_with_default(self.gconf.get_int, key)

    def set_int(self, key, value):
        self.gconf.set_int(self.path(key), value)

    def get_float(self, key):
        return self.get_with_default(self.gconf.get_float, key)

    def set_float(self, key, value):
        self.gconf.set_float(self.path(key), value)

    def get_string(self, key):
        return self.get_with_default(self.gconf.get_string, key)

    def set_string(self, key, value):
        self.gconf.set_string(self.path(key), value)

    def run(self):
        self.dialog.run()
        self.dialog.hide()

    def on_same_folder_as_input_toggled(self, button):
        if button.get_active():
            self.set_int("same-folder-as-input", 1)
            self.set_sensitive()
            self.update_example()
            
    def on_into_selected_folder_toggled(self, button):
        if button.get_active():
            self.set_int("same-folder-as-input", 0)
            self.set_sensitive()
            self.update_example()

    def on_choose_folder_clicked(self, button):
        ret = self.target_folder_chooser.run()
        self.target_folder_chooser.hide()
        if ret == gtk.RESPONSE_OK:
            folder = self.target_folder_chooser.get_filename()
            if folder:
                self.set_string("selected-folder", folder)
                self.update_selected_folder()
                self.update_example()

    def on_create_subfolders_toggled(self, button):
        if button.get_active():
            self.set_int("create-subfolders", 1)
        else:
            self.set_int("create-subfolders", 0)
        self.update_example()

    def on_subfolder_pattern_changed(self, combobox):
        self.set_int("subfolder-pattern-index", combobox.get_active())
        self.update_example()
        
    def get_subfolder_pattern(self):
        index = self.get_int("subfolder-pattern-index")
        if index < 0 or index >= len(self.subfolder_patterns):
            index = 0
        return self.subfolder_patterns[index][0]

    def on_basename_pattern_changed(self, combobox):
        self.set_int("name-pattern-index", combobox.get_active())
        self.update_example()

    def get_basename_pattern(self):
        index = self.get_int("name-pattern-index")
        if index < 0 or index >= len(self.basename_patterns):
            index = 0
        return self.basename_patterns[index][0]
        
    def UNUSED_on_replace_only_impossible_chars_toggled(self, button):
        if button.get_active():
            self.set_int("replace-messy-chars", 0)
            self.update_example()

    def on_replace_messy_chars_toggled(self, button):
        if button.get_active():
            self.set_int("replace-messy-chars", 1)
        else:
            self.set_int("replace-messy-chars", 0)
        self.update_example()

    def change_mime_type(self, mime_type):
        self.set_string("output-mime-type", mime_type)
        self.set_sensitive()
        self.update_example()
        tabs = {
                        "audio/x-vorbis": 0,
                        "audio/mpeg": 1,
                        "audio/x-flac": 2,
                        "audio/x-wav": 3,
        }
        self.quality_tabs.set_current_page(tabs[mime_type])
        
        #print _("setting mime:"), mime_type

    def on_output_mime_type_ogg_vorbis_toggled(self, button):
        if button.get_active():
            self.change_mime_type("audio/x-vorbis")

    def on_output_mime_type_flac_toggled(self, button):
        if button.get_active():
            self.change_mime_type("audio/x-flac")
        
    def on_output_mime_type_wav_toggled(self, button):
        if button.get_active():
            self.change_mime_type("audio/x-wav")

    def on_output_mime_type_mp3_toggled(self, button):
        if button.get_active():
            self.change_mime_type("audio/mpeg")

    def UNUSED_on_vorbis_quality_value_changed(self, combobox):
        self.set_int("vorbis-quality", combobox.get_active())
        
    def on_vorbis_quality_changed(self, combobox):
        quality = (0,0.2,0.4,0.6,0.8)
        self.set_float("vorbis-quality", quality[combobox.get_active()])
        
        self.update_example()

    def change_mp3_mode(self, mode):
    
        keys = { "cbr": 0, "abr": 1, "vbr": 2 }
        self.mp3_mode.set_active(keys[mode]);
    
        keys = { 
            "cbr": "mp3-cbr-quality",
            "abr": "mp3-abr-quality",
            "vbr": "mp3-vbr-quality",
        }
        quality = self.get_int(keys[mode])
        
        #print _("\nchange mp3 mode")
        #print _("quality: %f") % quality
        
        #~ quality_to_preset = {
            #~ "cbr": (64, 96, 128, 192, 256),
            #~ "abr": (64, 96, 128, 192, 256),
            #~ "vbr": (1, 3, 5, 7, 9), # inverted !
        #~ }

        quality_to_preset = {
            "cbr": {64:0, 96:1, 128:2, 192:3, 256:4},
            "abr": {64:0, 96:1, 128:2, 192:3, 256:4},
            "vbr": {9:0,   7:1,   5:2,   3:3,   1:4}, # inverted !
        }


        #~ active = 0
        #~ for i in quality_to_preset[mode]:
            #~ print "  " , quality , " <-> " , i
            #~ if quality <= i:
                #~ print _("I choose #%s = %s") % (active, quality_to_preset[mode][active])
                #~ break
            #~ active+=1
            
        #~ if mode == "vbr": 
            #~ active = 4-active
            
        if quality in quality_to_preset[mode]:
            #print "mp3 quality:", quality, mode, quality_to_preset[mode][quality]
            self.mp3_quality.set_active(quality_to_preset[mode][quality])
        
        self.update_example()

    def on_mp3_mode_changed(self, combobox):
        mode = ("cbr","abr","vbr")[combobox.get_active()]
        self.set_string("mp3-mode", mode)
        self.change_mp3_mode(mode)

    def on_mp3_quality_changed(self, combobox):
        keys = {
            "cbr": "mp3-cbr-quality",
            "abr": "mp3-abr-quality",
            "vbr": "mp3-vbr-quality"
        }
        quality = {
            "cbr": (64, 96, 128, 192, 256),
            "abr": (64, 96, 128, 192, 256),
            "vbr": (9, 7, 5, 3, 1),
        }
        mode = self.get_string("mp3-mode")
        self.set_int(keys[mode], quality[mode][combobox.get_active()])

        self.update_example()
        #print "%s[%d] = %s" % (keys[mode], combobox.get_active(), quality[mode][combobox.get_active()])


    def UNUSED_on_output_mime_type_changed(self, combobox):
        types = (
        ("audio/x-vorbis", ".ogg"),
        ("audio/mpeg", ".mp3"),
        ("audio/x-flac", ".flac"),
        ("audio/x-wav", ".wav")
        )
        self.handle_mime_type_button( types[combobox.get_active()][0],
                                      types[combobox.get_active()][1])


class ConverterQueueCanceled(SoundConverterException):

    """Exception thrown when a ConverterQueue is canceled."""

    def __init__(self):
        SoundConverterException.__init__(self, _("Convertion Canceled"), "")


class ConverterQueue(TaskQueue):

    """Background task for converting many files."""

    def __init__(self, window):
        TaskQueue.__init__(self)
        self.window = window
        self.overwrite_action = None
        self.reset_counters()
        
    def reset_counters(self):
        self.total_bytes = 0
        self.total_for_processed_files = 0
        self.overwrite_action = None

    def add(self, sound_file):
        output_filename = self.window.prefs.generate_filename(sound_file)
        
        path = urlparse.urlparse(output_filename) [2]
        
        path = urllib.unquote(path)
        
        exists = True
        try:
            gnomevfs.get_file_info(gnomevfs.URI(output_filename))
        except gnomevfs.NotFoundError:
            exists = False
                
        if exists:

            if self.overwrite_action != None:
                result = self.overwrite_action
            else:
                dialog = self.window.existsdialog

                dpath = os.path.basename(path)
                dpath = dpath.replace("&","&amp;")

                msg = \
                _("The output file <i>%s</i>\n exists already.\n Do you want to skip the file, overwrite it or cancel the conversion?\n") % \
                ( dpath )

                dialog.message.set_markup(msg)

                if self.overwrite_action != None:
                    dialog.apply_to_all.set_active(True)
                else:
                    dialog.apply_to_all.set_active(False)

                result = dialog.run()
                dialog.hide()

                if dialog.apply_to_all.get_active():
                    if result == 1 or result == 0:
                        self.overwrite_action = result
 

            if result == 1: 
                # overwrite
                #os.remove(path)
                gnomevfs.unlink(gnomevfs.URI(output_filename))
            elif result == 0: 
                # skip file
                return
            else:
                # cancel operation
                # TODO
                raise ConverterQueueCanceled()
                #self.stop()
            
        c = Converter(sound_file, output_filename, 
                      self.window.prefs.get_string("output-mime-type"))
        c.set_vorbis_quality(self.window.prefs.get_float("vorbis-quality"))
        
        quality = {
            "cbr": "mp3-cbr-quality",
            "abr": "mp3-abr-quality",
            "vbr": "mp3-vbr-quality"
        }
        mode = self.window.prefs.get_string("mp3-mode")
        c.set_mp3_mode(mode)
        c.set_mp3_quality(self.window.prefs.get_int(quality[mode]))
        TaskQueue.add(self, c)
        self.total_bytes += c.get_size_in_bytes()

    def work_hook(self, task):
        bytes = task.get_bytes_progress()
        self.window.set_progress(self.total_for_processed_files + bytes,
                                 self.total_bytes)

    def finish_hook(self, task):
        self.total_for_processed_files += task.get_size_in_bytes()

    def finish(self):
        TaskQueue.finish(self)
        self.reset_counters()
        self.window.set_progress(0, 0)
        self.window.set_sensitive()
        total_time = self.run_finish_times[4] - self.run_start_times[4]
        user_time = self.run_finish_times[0] - self.run_start_times[0]
        system_time = self.run_finish_times[1] - self.run_start_times[1]
        self.window.set_status(_("Conversion done. ( in %s )") % 
                               self.format_time(total_time))

    def format_time(self, seconds):
        units = [(86400, "d"),
                 (3600, "h"),
                 (60, "min"),
                 (1, "s")]
        seconds = round(seconds)
        result = []
        for factor, name in units:
            count = int(seconds / factor)
            seconds -= count * factor
            if count > 0 or (factor == 1 and not result):
                result.append("%d %s" % (count, name))
        assert seconds == 0
        return " ".join(result)

    def stop(self):
        TaskQueue.stop(self)
        self.window.set_progress(0, 0)
        self.window.set_sensitive()


class SoundConverterWindow:

    """Main application class."""

    sensitive_names = [ "remove", "stop_button", "convert_button" ]

    def __init__(self, glade):
    
        self.widget = glade.get_widget("window")
        self.filelist = FileList(self, glade)
        self.filelist_selection = self.filelist.widget.get_selection()
        self.filelist_selection.connect("changed", self.selection_changed)
        self.existsdialog = glade.get_widget("existsdialog")
        self.existsdialog.message = glade.get_widget("exists_message")
        self.existsdialog.apply_to_all = glade.get_widget("apply_to_all")
        self.existslabel = glade.get_widget("existslabel")
        self.progressbar = glade.get_widget("progressbar")
        self.status = glade.get_widget("statustext")
        self.about = glade.get_widget("about")
        self.prefs = PreferencesDialog(glade)
        
        self.addchooser = gtk.FileChooserDialog(_("Add files..."),
                                                self.widget,
                                                gtk.FILE_CHOOSER_ACTION_OPEN,
                                                (gtk.STOCK_CANCEL, 
                                                    gtk.RESPONSE_CANCEL,
                                                 gtk.STOCK_OPEN,
                                                    gtk.RESPONSE_OK))
        self.addchooser.set_select_multiple(True)

        self.addfolderchooser = gtk.FileChooserDialog(_("Add Folder..."),
                                                self.widget,
                                                gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                                                (gtk.STOCK_CANCEL, 
                                                    gtk.RESPONSE_CANCEL,
                                                 gtk.STOCK_OPEN,
                                                    gtk.RESPONSE_OK))

        self.connect(glade, [self.prefs])
        
        self.about.set_property("name", NAME)
        self.about.set_property("version", VERSION)

        self.converter = ConverterQueue(self)
        
        self.sensitive_widgets = {}
        for name in self.sensitive_names:
            self.sensitive_widgets[name] = glade.get_widget(name)
        self.set_sensitive()

    # This bit of code constructs a list of methods for binding to Gtk+
    # signals. This way, we don't have to maintain a list manually,
    # saving editing effort. It's enough to add a method to the suitable
    # class and give the same name in the .glade file.
    
    def connect(self, glade, objects):
        dict = {}
        for object in [self] + objects:
            for name, member in inspect.getmembers(object):
                dict[name] = member
        glade.signal_autoconnect(dict)

    def close(self, *args):
        self.converter.stop()
        self.widget.destroy()
        gtk.main_quit()
        return gtk.TRUE

    on_window_delete_event = close
    on_quit_activate = close
    on_quit_button_clicked = close

    def on_add_activate(self, *args):
        ret = self.addchooser.run()
        self.addchooser.hide()
        if ret == gtk.RESPONSE_OK:
            for uri in self.addchooser.get_uris():
                self.filelist.add_file(SoundFile(uri))
        self.set_sensitive()

    def on_addfolder_activate(self, *args):
        #print "add_folder"
        
        ret = self.addfolderchooser.run()
        self.addfolderchooser.hide()
        if ret == gtk.RESPONSE_OK:
            folder = self.addfolderchooser.get_filename()
        
            for root, dirs, files in os.walk(folder):
                for name in files:
                    f = os.path.join(root, name)
                    self.filelist.add_file(SoundFile(f))
        
        self.set_sensitive()

    def on_remove_activate(self, *args):
        model, paths = self.filelist_selection.get_selected_rows()
        while paths:
            iter = self.filelist.model.get_iter(paths[0])
            self.filelist.remove(iter)
            model, paths = self.filelist_selection.get_selected_rows()
        self.set_sensitive()

    def on_convert_button_clicked(self, *args):
        try:
            for fields in self.filelist.get_files():
                self.converter.add(fields["META"])
        except ConverterQueueCanceled:
            print _("canceling conversion.")
        else:
            self.converter.run()
            self.set_sensitive()
        
    def on_stop_button_clicked(self, *args):
        self.converter.stop()
        self.set_sensitive()

    def on_select_all_activate(self, *args):
        self.filelist.widget.get_selection().select_all()
        
    def on_clear_activate(self, *args):
        self.filelist.widget.get_selection().unselect_all()

    def on_preferences_activate(self, *args):
        self.prefs.run()
        
    on_prefs_button_clicked = on_preferences_activate

    def on_about_activate(self, *args):
        about = gtk.glade.XML(GLADE, "about").get_widget("about")
        about.set_property("name", NAME)
        about.set_property("version", VERSION)
        about.set_property("translator_credits", TRANSLATORS)
        about.show()
        # TODO
        #self.about.show()

    def selection_changed(self, *args):
        self.set_sensitive()

    def set_widget_sensitive(self, name, sensitivity):
        self.sensitive_widgets[name].set_sensitive(sensitivity)

    def set_sensitive(self):
        self.set_widget_sensitive("remove", 
            self.filelist_selection.count_selected_rows() > 0)
        self.set_widget_sensitive("convert_button", 
                                  self.filelist.is_nonempty() and
                                  not self.converter.is_running())
        self.set_widget_sensitive("stop_button", 
                                  self.converter.is_running())

    def set_progress(self, done_so_far, total):
        if total == 0:
            self.progressbar.set_text("")
            self.progressbar.set_fraction(0.0)
        else:
            fraction = float(done_so_far) / total
            self.progressbar.set_fraction(fraction)
            self.progressbar.set_text("%.1f %%" % (100.0 * fraction))

    def set_status(self, text):
        self.status.set_text(text)


def gui_main(input_files):
    gnome.init(NAME, VERSION)
    glade = gtk.glade.XML(GLADE)
    win = SoundConverterWindow(glade)
    global error
    error = ErrorDialog(glade)
    for input_file in input_files:
        win.filelist.add_file(input_file)
    win.set_sensitive()
    gtk.main()


def cli_tags_main(input_files):
    global error
    error = ErrorPrinter()
    for input_file in input_files:
        if not get("quiet"):
            print input_file.get_uri()
        t = TagReader(input_file)
        t.setup()
        while t.do_work():
            pass
        t.finish()
        if not get("quiet"):
            keys = input_file.keys()
            keys.sort()
            for key in keys:
                print "  %s: %s" % (key, input_file[key])


class CliProgress:

    def __init__(self):
        self.current_text = ""
        
    def show(self, new_text):
        if new_text != self.current_text:
            self.clear()
            sys.stdout.write(new_text)
            sys.stdout.flush()
            self.current_text = new_text
    
    def clear(self):
        sys.stdout.write("\b \b" * len(self.current_text))
        sys.stdout.flush()


def cli_convert_main(input_files):
    global error
    error = ErrorPrinter()

    output_type = get("cli-output-type")
    output_suffix = get("cli-output-suffix")
    
    generator = TargetNameGenerator()
    generator.set_target_suffix(output_suffix)
    
    progress = CliProgress()
    
    queue = TaskQueue()
    for input_file in input_files:
        output_name = generator.get_target_name(input_file)
        queue.add(Converter(input_file, output_name, output_type))
    
    queue.setup()
    while queue.do_work():
        t = queue.get_current_task()
        if not get("quiet"):
            progress.show("%s: %.1f %%" % (t.get_input_uri()[-65:], 
                                           t.get_progress()))
    if not get("quiet"):
        progress.clear()


settings = {
    "mode": "gui",
    "quiet": False,
    "cli-output-type": "audio/x-vorbis",
    "cli-output-suffix": ".ogg",
}


def set(key, value):
    assert key in settings
    settings[key] = value


def get(key):
    assert key in settings
    return settings[key]


def print_help(*args):
    print _("Usage: %s [options] [soundfile ...]") % sys.argv[0]
    for short, long, func, doc in options:
        print
        if short[-1] == ":":
            print "  -%s arg, --%sarg" % (short[:1], long)
        else:
            print "  -%s, --%s" % (short[:1], long)
        for line in textwrap.wrap(doc):
            print "    %s" % line
    sys.exit(0)


options = [

    ("h", "help", print_help,
     _("Print out a usage summary.")),

    ("b", "batch", lambda optarg: set("mode", "batch"),
     _("Convert in batch mode, from command line, without a graphical user\n interface. You can use this from, say, shell scripts.")),

    ("m:", "mime-type=", lambda optarg: set("cli-output-type", optarg),
     _("Set the output MIME type for batch mode. The default is\n %s . Note that you probably want to set\n the output suffix as well.") % get("cli-output-type")),
     
    ("q", "quiet", lambda optarg: set("quiet", True),
     _("Be quiet. Don't write normal output, only errors.")),

    ("s:", "suffix=", lambda optarg: set("cli-output-suffix", optarg),
     _("Set the output filename suffix for batch mode. The default is \n %s . Note that the suffix does not affect\n the output MIME type.") % get("cli-output-suffix")),

    ("t", "tags", lambda optarg: set("mode", "tags"),
     _("Show tags for input files instead of converting them. This indicates \n command line batch mode and disables the graphical user interface.")),

    ]


def main():
    shortopts = "".join(map(lambda opt: opt[0], options))
    longopts = map(lambda opt: opt[1], options)
    opts, args = getopt.getopt(sys.argv[1:], shortopts, longopts)
    for opt, optarg in opts:
        for tuple in options:
            short = "-" + tuple[0][:1]
            long = "--" + tuple[1]
            if long.endswith("="):
                long = long[:-1]
            if opt in [short, long]:
                tuple[2](optarg)
                break
    if 0:
        print
        for key in settings:
            print key, settings[key]
        return
    
    
    args = map(filename_to_uri, args)
    args = map(SoundFile, args)

    if get("mode") == "gui":
        gui_main(args)
    elif get("mode") == "tags":
        cli_tags_main(args)
    else:
        cli_convert_main(args)


if __name__ == "__main__":
    main()
