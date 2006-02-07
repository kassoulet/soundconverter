#!/usr/bin/python
# -*- coding: latin-1 -*-
#
# SoundConverter - GNOME application for converting between audio formats. 
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2006 Gautier Portet
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
VERSION = "0.9.0-wip"
GLADE = "soundconverter.glade"

# Python standard stuff.
import sys
import os
import inspect
import getopt
import textwrap
import urlparse
import string
import thread
import urllib
import time

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

try:
	# gnome.vfs is deprecated
	import gnomevfs
except ImportError:
	import gnome.vfs
	gnomevfs = gnome.vfs

# This is missing from gst, for some reason.
FORMAT_PERCENT_SCALE = 10000

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

TRANSLATORS = _("""Guillaume Bedot <guillaume.bedot wanadoo.fr> (french)
Dominik Zabłotny <dominz wp.pl> (polish) 
Jonh Wendell <wendell bani.com.br> (Brazilian)
""")

# Names of columns in the file list
VISIBLE_COLUMNS = ["filename"]
ALL_COLUMNS = VISIBLE_COLUMNS + ["META"] 

MP3_CBR, MP3_ABR, MP3_VBR = range(3)

# add here any format you want to be read
mime_whitelist = (
	"audio/", 
	"video/", 
	"application/ogg", 
	"application/x-id3",
	"application/x-ape",
	"application/vnd.rn-realmedia",
	"application/x-shockwave-flash",
)

# Name and pattern for CustomFileChooser
filepattern = (
	("All files","*.*"),
	("MPEG 1 Layer 3 files","*.mp3"),
	("Ogg Vorbis files","*.ogg"),
	("iTunes AAC files","*.m4a"),
	("WAVEform audio format","*.wav"),
	("Advanced Audio Coding","*.aac"),
	("Free Lossless Audio Codec","*.flac"),
	("Audio Codec 3","*.ac3")
)

def vfs_walk(uri):
	"""similar to os.path.walk, but with gnomevfs.
	
	uri -- the base folder uri.
	return a list of uri.
	
	"""
	if str(uri)[-1] != '/':
		uri = uri.append_string("/")

	info = gnomevfs.get_file_info(uri, gnomevfs.FILE_INFO_GET_MIME_TYPE)
	filelist = []	

	try:
		dirlist = gnomevfs.open_directory(uri)
	except:
		pass
		log(_("skipping: '%s'") % uri)
		return filelist
		
	for file_info in dirlist:
		if file_info.name[0] == ".":
			continue
	
		if file_info.type == gnomevfs.FILE_TYPE_DIRECTORY:
			filelist.extend(
				vfs_walk(uri.append_path(file_info.name)) )

		if file_info.type == gnomevfs.FILE_TYPE_REGULAR:
			filelist.append( str(uri.append_file_name(file_info.name)) )
	return filelist

def vfs_makedirs(path_to_create):
	"""Similar to os.makedirs, but with gnomevfs"""
	
	uri = gnomevfs.URI(path_to_create)
	path = uri.path

	# start at root
	uri =  uri.resolve_relative("/")
	
	for folder in path.split("/"):
		if not folder:
			continue
		uri = uri.append_string(folder)
		try:
			gnomevfs.make_directory(uri, 0777)
		except gnomevfs.FileExistsError:
			pass
		except :
			return False
	return True	

def markup_escape(str):
	str = "&amp;".join(str.split("&"))
	str = "&lt;".join(str.split("<"))
	str = "&gt;".join(str.split(">"))
	return str

def filename_escape(str):
	str = str.replace("'","\'")
	str = str.replace("\"","\\\"")
	str = str.replace("!","\!")
	return str

def log(message):
	if get("quiet") == False:
		print message

def sleep(duration):
	start = time.time()
	while time.time() < start + duration:
		while gtk.events_pending():
			gtk.main_iteration(False)
		time.sleep(0.010)


def UNUSED_display_from_mime(mime):
	# TODO
	mime_dict = {
		"application/ogg": "Ogg Vorbis",
		"audio/x-wav": "MS WAV",
		"audio/mpeg": "MPEG 1 Layer 3 (MP3)",
		"audio/x-flac": "FLAC",
		"audio/x-musepack": "MusePack",
		"audio/x-au": "AU",
	}
	return mime_dict[mime]


class SoundConverterException(Exception):

	def __init__(self, primary, secondary):
		Exception.__init__(self)
		self.primary = primary
		self.secondary = secondary
		

def filename_to_uri(filename):
	return "file://" + urllib.quote(os.path.abspath(filename))


class SoundFile:

	"""Meta data information about a sound file (uri, tags)."""

	def __init__(self, base_path, filename=None):
		if filename:
			self.base_path = base_path
			self.filename = filename
			self.uri = os.path.join(base_path, filename)
		else:
			self.uri = base_path 
			self.base_path, self.filename = os.path.split(self.uri)
			self.base_path += "/"
	
		self.tags = {
			"track-number": 0,
			"title":  "Unknown Title",
			"artist": "Unknown Artist",
			"album":  "Unknown Album",
		}
		self.have_tags = False
		self.tags_read = False
		
	def get_uri(self):
		return self.uri
		
	def get_base_path(self):
		return self.base_path
		
	def get_filename(self):
		return self.filename
		
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

		root = urlparse.urlsplit(sound_file.get_base_path())[2]
		basename, ext = os.path.splitext(sound_file.get_filename())
		
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
		self.paused = False
		self.run_start_time = time.time()
		self.current_paused_time = 0
		self.paused_time = 0
		self.id = gobject.idle_add(self.do_work, priority=gobject.PRIORITY_LOW)
	
	def do_work(self):
		"""Do some work by calling work(). Call finish() if work is done."""
		try:
			if self.paused:
				if not self.current_paused_time:
					self.current_paused_time = time.time()
				return True
			else:
				if self.current_paused_time:
					self.paused_time += time.time() - self.current_paused_time
					self.current_paused_time = 0
					
			if self.work():
				return True
			else:
				self.run_finish_time = time.time()
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
		self.tasks_number=0
		self.tasks_current=0
		
	def is_running(self):
		return self.running

	def add(self, task):
		self.tasks.append(task)
		self.tasks_number += 1
		
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
					self.tasks_current += 1
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
		self.pipeline = None #gst.Pipeline()
		self.command = ""
		self.parsed = False
		self.signals = []
		self.processing = False
		
	def setup(self):
		self.play()
		
	def work(self):
		if self.pipeline.get_state() == gst.STATE_NULL:
			print "error: pipeline.state == null"
			#return False
		return self.pipeline.iterate()

	def finish(self):
		self.stop_pipeline()

	def add_command(self, command):
		if self.command:
			self.command += " ! "
		self.command += command

	def add_signal(self, name, signal, callback):
		self.signals.append( (name, signal, callback,) )

	def toggle_pause(self, paused):
		if paused:
			self.pipeline.set_state(gst.STATE_PAUSED)
		else:
			self.pipeline.set_state(gst.STATE_PLAYING)

	def play(self):
		if not self.parsed:
			print "launching: '%s'" % self.command
			self.pipeline = gst.parse_launch(self.command)
			for name, signal, callback in self.signals:
				self.pipeline.get_by_name(name).connect(signal,callback)
			self.parsed = True
		else:
			print "ERROR: ALREADY PARSED!!!"
		
		self.pipeline.set_state(gst.STATE_PLAYING)

	def stop_pipeline(self):
		self.pipeline.set_state(gst.STATE_NULL)

	def get_progress(self):
		if not self.processing:
			return 0
		element = self.pipeline.get_by_name("src")
		return element.query(gst.QUERY_POSITION, gst.FORMAT_PERCENT) 

	def get_bytes_progress(self):
		if not self.processing:
			return 0
		element = self.pipeline.get_by_name("src")
		return element.query(gst.QUERY_POSITION, gst.FORMAT_BYTES) 

class TypeFinder(Pipeline):
	def __init__(self, sound_file):
		Pipeline.__init__(self)
		self.sound_file = sound_file
		self.found_type = ""
	
		command = 'gnomevfssrc location="%s" ! typefind name=typefinder' % \
			self.sound_file.get_uri()
		self.add_command(command)
		self.add_signal("typefinder", "have-type", self.have_type)

	def set_found_type_hook(self, found_type_hook):
		self.found_type_hook = found_type_hook
	
	def have_type(self, typefind, probability, caps):
		mime_type = caps.to_string()
		self.found_type = None
		for t in mime_whitelist:
			if t in mime_type:
				self.found_type = mime_type
		if not self.found_type:
			log("Mime type skipped: %s (mail us if this is an error)" % mime_type)
	
	def work(self):
		return Pipeline.work(self) and not self.found_type

	def finish(self):
		Pipeline.finish(self)
		if self.found_type_hook and self.found_type:
			self.found_type_hook(self.sound_file, self.found_type)


class Decoder(Pipeline):

	"""A GstPipeline background task that decodes data and finds tags."""

	def __init__(self, sound_file):
		Pipeline.__init__(self)
		self.sound_file = sound_file
		
		command = 'gnomevfssrc location="%s" name=src ! decodebin name=decoder' % \
			self.sound_file.get_uri()
		self.add_command(command)
		self.add_signal("decoder", "found-tag", self.found_tag)
		self.add_signal("decoder", "new-decoded-pad", self.new_decoded_pad)
		
		# TODO add error management

	def have_type(self, typefind, probability, caps):
		pass

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
			print "notfound:", uri
			return 0

class TagReader(Decoder):

	"""A GstPipeline background task for finding meta tags in a file."""

	def __init__(self, sound_file):
		Decoder.__init__(self, sound_file)
		self.found_tag_hook = None
		self.found_tags = False
		self.run_start_time = time.time()

	def set_found_tag_hook(self, found_tag_hook):
		self.found_tag_hook = found_tag_hook


	def found_tag(self, decoder, something, taglist):

		self.sound_file.add_tags(taglist)

		# tags from ogg vorbis files comes with two callbacks,
		# the first callback containing just the stream serial number.
		# The second callback contains the tags we're interested in.
		if taglist.has_key('serial'):
			return

		self.found_tags = True
		self.sound_file.have_tags = True

	def work(self):
		if time.time()-self.run_start_time > 5:
			# stop looking for tags after 5s 
			return False
		return Decoder.work(self) and not self.found_tags

	def finish(self):
		Decoder.finish(self)
		self.sound_file.tags_read = True
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

		self.converting = True
		
		self.output_filename = output_filename
		self.output_type = output_type
		self.vorbis_quality = None
		self.mp3_bitrate = None
		self.mp3_mode = None
		self.mp3_quality = None
		self.added_pad_already = False

	def init(self):
		self.encoders = {
			"audio/x-vorbis": self.add_oggvorbis_encoder,
			"audio/x-flac": self.add_flac_encoder,
			"audio/x-wav": self.add_wav_encoder,
			"audio/mpeg": self.add_mp3_encoder,
		}

		self.add_command("audioconvert")
		self.add_command("audioscale")
		
		encoder = self.encoders[self.output_type]()
		if not encoder:
			# TODO: add proper error management when an encoder cannot be created
			dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR,
						gtk.BUTTONS_OK, _("Cannot create a decoder for '%s' format.") % \
						self.output_type )
			dialog.run()
			dialog.hide()
			return
			
		self.add_command(encoder)
		
		uri = gnomevfs.URI(self.output_filename)
		dirname = uri.parent
		if dirname and not gnomevfs.exists(dirname):
			log(_("Creating folder: '%s'") % dirname)
			if not vfs_makedirs(str(dirname)):
				# TODO add error management
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR,
							gtk.BUTTONS_OK, _("Cannot create '%s' folder.") % \
							dirname )
				dialog.run()
				dialog.hide()
				return
	
		self.add_command('gnomevfssink location=%s' % uri)
		log( _("Writing to: '%s'") % urllib.unquote(self.output_filename) )
	
	def new_decoded_pad(self, decoder, pad, is_last):
		if self.added_pad_already:
			return
		if not pad.get_caps():
			return
		if "audio" not in pad.get_caps()[0].get_name():
			return
		print "new_decoded_pad"
		self.added_pad_already = True
		self.processing = True

	def set_vorbis_quality(self, quality):
		self.vorbis_quality = quality

	def set_mp3_mode(self, mode):
		self.mp3_mode = mode

	def set_mp3_quality(self, quality):
		self.mp3_quality = quality

	def add_flac_encoder(self):
		return "flacenc"

	def add_wav_encoder(self):
		return "wavenc"

	def add_oggvorbis_encoder(self):
		cmd = "vorbisenc"
		if self.vorbis_quality is not None:
			cmd += " quality=%s" % self.vorbis_quality
		return cmd

	def add_mp3_encoder(self):
	
		cmd = "lame quality=2 "
		
		if self.mp3_mode is not None:
			properties = {
				"cbr" : (0,"bitrate"),
				"abr" : (3,"vbr-mean-bitrate"),
				"vbr" : (4,"vbr-quality")
			}

			if properties[self.mp3_mode][0]:
				cmd += "xingheader=true "
			
			cmd += "vbr=%s " % properties[self.mp3_mode][0]
			if self.mp3_quality == 9:
				# GStreamer set max bitrate to 320 but lame uses
				# mpeg2 with vbr-quality==9, so max bitrate is 160
				cmd += "vbr-max-bitrate=160 "
			
			cmd += "%s=%s " % (properties[self.mp3_mode][1], self.mp3_quality)
	
		return cmd

class FileList:
	"""List of files added by the user."""

	# List of MIME types which we accept for drops.
	drop_mime_types = ["text/uri-list", "text/plain", "STRING"]

	def __init__(self, window, glade):
		self.window = window
		self.tagreaders  = TaskQueue()
		self.typefinders = TaskQueue()
		
		self.filelist={}
		
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
										markup=ALL_COLUMNS.index(name))
			self.widget.append_column(column)
	
	def drag_data_received(self, widget, context, x, y, selection, 
						   mime_id, time):

		if mime_id >= 0 and mime_id < len(self.drop_mime_types):
			mime_type = self.drop_mime_types[mime_id]
			file_list = []
			for uri in selection.data.split("\n"):
				uri = uri.strip()
				if uri:
					info = gnomevfs.get_file_info(uri, gnomevfs.FILE_INFO_DEFAULT)
					if info.type == gnomevfs.FILE_TYPE_DIRECTORY:
						file_list.extend(vfs_walk(gnomevfs.URI(uri)))
					else:
						file_list.append(uri)
			context.finish(True, False, time)
			base = os.path.commonprefix(file_list)
			[self.add_file(SoundFile(base, uri[len(base):])) for uri in file_list]

	def get_files(self):
		files = []
		iter = self.model.get_iter_first()
		while iter:
			file = {}
			for c in ALL_COLUMNS:
				file[c] = self.model.get_value(iter, ALL_COLUMNS.index(c))
			files.append(file["META"])

			iter = self.model.iter_next(iter)
		return files
	
	def found_type(self, sound_file, mime):

		self.append_file(sound_file)
		self.window.set_sensitive()

		tagreader = TagReader(sound_file)
		tagreader.set_found_tag_hook(self.append_file_tags)

		self.tagreaders.add(tagreader)
		if not self.tagreaders.is_running():
			self.tagreaders.run()
	
	def add_file(self, sound_file):

		if sound_file.get_uri() in self.filelist:
			log("file already present: '%s'" % sound_file.get_uri())
			return 

		self.filelist[sound_file.get_uri()] = True
		typefinder = TypeFinder(sound_file)
		typefinder.set_found_type_hook(self.found_type)
		self.typefinders.add(typefinder)
		if not self.typefinders.is_running():
			self.typefinders.run()
			
	def add_folder(self, folder):

		base = folder
		filelist = vfs_walk(gnomevfs.URI(folder))
		for f in filelist:
			f = f[len(base)+1:]
			self.add_file(SoundFile(base+"/", f))
				
	def format_cell(self, sound_file):
		
		template_tags    = "%(artist)s - <i>%(album)s</i> - <b>%(title)s</b>\n<small>%(filename)s</small>"
		template_loading = "<i>%s</i>\n<small>%%(filename)s</small>" \
							% _("loading tags...")
		template_notags  = '<span foreground="red">%s</span>\n<small>%%(filename)s</small>' \
							% _("no tags")

		params = {}
		params["filename"] = markup_escape(urllib.unquote(sound_file.get_filename()))
		for item in ("title", "artist", "album"):
			params[item] = markup_escape(sound_file.get_tag(item))
	
		try:	
			if sound_file.have_tags:
				s = template_tags % params
			else:
				if sound_file.tags_read:
					s = template_notags % params
				else:
					s = template_loading % params
		except UnicodeDecodeError:
			str = ""
			for c in markup_escape(urllib.unquote(sound_file.get_uri())):
				if ord(c) < 127:
					str += c
				else:
					str += '<span foreground="yellow" background="red"><b>!</b></span>'

			error.show(_("Invalid character in filename!"), str)
			sys.exit(1)
				
		return s

	def append_file(self, sound_file):

		iter = self.model.append()
		sound_file.model = iter
		self.model.set(iter, 0, self.format_cell(sound_file))
		self.model.set(iter, 1, sound_file)
	
	
	def append_file_tags(self, tagreader):
		sound_file = tagreader.get_sound_file()


		fields = {}
		for key in ALL_COLUMNS:
			fields[key] = _("unknown")
		fields["META"] = sound_file
		fields["filename"] = urllib.unquote(sound_file.get_filename())

		self.model.set(sound_file.model, 0, self.format_cell(sound_file))

		self.window.set_sensitive()

	def remove(self, iter):
		uri = self.model.get(iter, 1)[0].get_uri()
		del self.filelist[uri]
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
		"mp3-mode": "vbr",			# 0: cbr, 1: abr, 2: vbr
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
			log("converting old vorbis setting...")
			old_quality = self.get_int("vorbis-quality")
			self.gconf.unset(self.path("vorbis-quality"))
			quality_setting = (0,0.2,0.3,0.6,0.8)
			self.set_float("vorbis-quality", quality_setting[old_quality])
			
		# mp3 quality was stored as an int enum
		cbr = self.get_int("mp3-cbr-quality")
		if cbr <= 4:
			log("converting old mp3 quality setting... (%d)" % cbr)

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
			log("converting old mp3 mode setting...")
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
			log("LAME GStreamer plugin not found, desactivating MP3 output.")
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
			"artist": "<b>{Artist}</b>", 
			"title": "<b>{Title}</b>", 
			"album": "<b>{Album}</b>",
			"track-number": 1L,
			"track-count": 11L,
		})
		self.example.set_markup(self.generate_filename(sound_file))
		
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
			path, filename = os.path.split(sound_file.get_filename())
			path = ""
		
			generator.set_folder(os.path.join(self.get_string("selected-folder"), path))
			if self.get_int("create-subfolders"):
				generator.set_subfolder_pattern(
					self.get_subfolder_pattern())
		generator.set_basename_pattern(self.get_basename_pattern())
		generator.set_replace_messy_chars(
			self.get_int("replace-messy-chars"))

		return generator.get_target_name(sound_file)

	def set_sensitive(self):
	
		#TODO
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
		
		quality_to_preset = {
			"cbr": {64:0, 96:1, 128:2, 192:3, 256:4},
			"abr": {64:0, 96:1, 128:2, 192:3, 256:4},
			"vbr": {9:0,   7:1,	  5:2,	 3:3,	1:4}, # inverted !
		}
			
		if quality in quality_to_preset[mode]:
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
			gnomevfs.get_file_info(gnomevfs.URI((output_filename)))
		except gnomevfs.NotFoundError:
			exists = False
				
		if exists:
			if self.overwrite_action != None:
				result = self.overwrite_action
			else:
				dialog = self.window.existsdialog

				dpath = os.path.basename(path)
				dpath = markup_escape(dpath)

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
				try:
					gnomevfs.unlink(gnomevfs.URI(output_filename))
				except gnomevfs.NotFoundError:
					pass
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
		c.init()
		TaskQueue.add(self, c)
		self.total_bytes += c.get_size_in_bytes()

	def work_hook(self, task):
		t = self.get_current_task()
		f = ""
		if t:
			f = urllib.unquote(t.sound_file.get_filename())
			
		bytes = task.get_bytes_progress()
		#print "work: %s+%s/%s" % (self.total_for_processed_files, bytes, self.total_bytes)
		self.window.set_progress(self.total_for_processed_files + bytes,
							 self.total_bytes, f)

	def finish_hook(self, task):
		#print "finished: %d+=%d" % (self.total_for_processed_files, task.get_size_in_bytes())
		self.total_for_processed_files += task.get_size_in_bytes()

	def finish(self):
		TaskQueue.finish(self)
		self.reset_counters()
		self.window.set_progress(0, 0)
		self.window.set_sensitive()
		self.window.conversion_ended()
		total_time = self.run_finish_time - self.run_start_time
		self.window.set_status(_("Conversion done, in %s") % 
							   self.format_time(total_time))

	def format_time(self, seconds):
		units = [(86400, "d"),
				 (3600, "h"),
				 (60, "m"),
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

class CustomFileChooser:
	"""
	Custom file chooser.\n
	"""
	def __init__(self):
		"""
		Constructor
		Load glade object, create a combobox
		"""
		xml = gtk.glade.XML(GLADE,"custom_file_chooser")
		self.dlg = xml.get_widget("custom_file_chooser")
		self.dlg.set_title(_("Open a file"))
		
		# setup
		self.fcw = xml.get_widget("filechooserwidget")
		self.fcw.set_local_only(False)
		self.fcw.set_select_multiple(True)
		
		self.pattern = []
		
		# Create combobox model
		self.combo = xml.get_widget("filtercombo")
		self.combo.connect("changed",self.on_combo_changed)
		self.store = gtk.ListStore(str)
		self.combo.set_model(self.store)
		combo_rend = gtk.CellRendererText()
		self.combo.pack_start(combo_rend, True)
		self.combo.add_attribute(combo_rend, 'text', 0)
	
		# get all (gstreamer) knew files Todo
		for files in filepattern:
			self.add_pattern(files[0],files[1])
		self.combo.set_active(0)
		
	def add_pattern(self,name,pat):
		"""
		Add a new pattern to the combobox.
		@param name: The pattern name.
		@type name: string
		@param pat: the pattern
		@type pat: string
		"""
		self.pattern.append(pat)
		self.store.append(["%s (%s)" %(name,pat)])
		
	def on_combo_changed(self,w):
		"""
		Callback for combobox "changed" signal\n
		Set a new filter for the filechooserwidget
		"""
		filter = gtk.FileFilter()
		filter.add_pattern(self.pattern[self.combo.get_active()])
		self.fcw.set_filter(filter)
		
	def run(self):
		"""
		Display the dialog
		"""
		return self.dlg.run()
		
	def hide(self):
		"""
		Hide the dialog
		"""
		self.dlg.hide()
		
	def get_uris(self):
		"""
		Return all the selected uris
		"""
		return self.fcw.get_uris()
		
		
class SoundConverterWindow:

	"""Main application class."""

	sensitive_names = [ "remove", "convert_button" ]
	unsensitive_when_converting = [ "remove", "prefs_button" ,"toolbutton_addfile", "toolbutton_addfolder", "filelist", "menubar" ]

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

		self.progressdialog = glade.get_widget("progressdialog")
		self.progressfile = glade.get_widget("label_currentfile")

		self.addchooser = CustomFileChooser()
		
		self.addfolderchooser = gtk.FileChooserDialog(_("Add Folder..."),
												self.widget,
												gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
												(gtk.STOCK_CANCEL, 
													gtk.RESPONSE_CANCEL,
													gtk.STOCK_OPEN,
													gtk.RESPONSE_OK))
		self.addfolderchooser.set_select_multiple(True)
		self.addfolderchooser.set_local_only(False)

		self.connect(glade, [self.prefs])
		
		self.about.set_property("name", NAME)
		self.about.set_property("version", VERSION)

		self.convertion_waiting = False

		self.converter = ConverterQueue(self)
		
		self._lock_convert_button = False
		
		self.sensitive_widgets = {}
		for name in self.sensitive_names:
			self.sensitive_widgets[name] = glade.get_widget(name)
		for name in self.unsensitive_when_converting:
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
		return True 

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
		ret = self.addfolderchooser.run()
		self.addfolderchooser.hide()
		if ret == gtk.RESPONSE_OK:
			folders = self.addfolderchooser.get_uris()
			
			base,notused = os.path.split(os.path.commonprefix(folders))
			filelist = []
			for folder in folders:
				filelist.extend(vfs_walk(gnomevfs.URI(folder)))
			for f in filelist:
				f = f[len(base)+1:]
				self.filelist.add_file(SoundFile(base+"/", f))
		self.set_sensitive()

	def on_remove_activate(self, *args):
		model, paths = self.filelist_selection.get_selected_rows()
		while paths:
			iter = self.filelist.model.get_iter(paths[0])
			self.filelist.remove(iter)
			model, paths = self.filelist_selection.get_selected_rows()
		self.set_sensitive()

	def do_convert(self):
		try:
			for sound_file in self.filelist.get_files():
				self.converter.add(sound_file)
		except ConverterQueueCanceled:
			print _("canceling conversion.")
		else:
			self.set_status("")
			self.converter.run()
			self.convertion_waiting = False
			self.set_sensitive()
		return False

	def wait_tags_and_convert(self):
		not_ready = [s for s in self.filelist.get_files() if not s.tags_read]
		if not_ready:
			self.progressbar.pulse()
			return True

		self.do_convert()
		return False
			

	def on_convert_button_clicked(self, *args):
		if self._lock_convert_button:
			return

		if not self.converter.is_running():
			self.progressdialog.show()
			self.progressdialog.set_transient_for(self.widget)
			self.widget.set_sensitive(False)
		
			self.convertion_waiting = True
			self.set_status(_("Waiting for tags..."))
			
			gobject.timeout_add(100, self.wait_tags_and_convert)
		else:
			self.converter.paused = not self.converter.paused
			if self.converter.paused:
				self.set_status(_("Paused"))
			else: 
				self.set_status("") 
		self.set_sensitive()

	def on_button_pause_clicked(self, *args):
		self.converter.paused = not self.converter.paused
		if self.converter.paused:
			self.display_progress(_("Paused"))

	def on_button_cancel_clicked(self, *args):
		self.converter.stop()
		self.set_status(_("Canceled")) 
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
		about = gtk.glade.XML(GLADE, "about").get_widget("about")
		about.set_property("name", NAME)
		about.set_property("version", VERSION)
		about.set_property("translator_credits", TRANSLATORS)
		about.show()

	def selection_changed(self, *args):
		self.set_sensitive()

	def conversion_ended(self):
		self.progressdialog.hide()
		self.widget.set_sensitive(True)

	def set_widget_sensitive(self, name, sensitivity):
		self.sensitive_widgets[name].set_sensitive(sensitivity)

	def set_sensitive(self):

		[self.set_widget_sensitive(w, not self.converter.is_running()) 
			for w in self.unsensitive_when_converting]

		self.set_widget_sensitive("remove", 
			self.filelist_selection.count_selected_rows() > 0)
		self.set_widget_sensitive("convert_button", 
								  self.filelist.is_nonempty())

		self._lock_convert_button = True
		self.sensitive_widgets["convert_button"].set_active(
			self.converter.is_running() and not self.converter.paused )
		self._lock_convert_button = False
	
	def display_progress(self, remaining):
		self.progressbar.set_text("Converting file %d of %d  (%s)" % ( self.converter.tasks_current+1, self.converter.tasks_number, remaining ))
		
	
	def set_progress(self, done_so_far, total, current_file=""):
		if total == 0:
			self.progressbar.set_text("")
			self.progressbar.set_fraction(0.0)
			return
		if done_so_far == 0:
			return
			
		fraction = float(done_so_far) / total
		self.progressbar.set_fraction(fraction)
		t = time.time() - self.converter.run_start_time - self.converter.paused_time
		r = (t / fraction - t)
		s = r%60
		m = r/60
		remaining = "%d:%02d left" % (m,s)
		self.display_progress(remaining)
		self.progressfile.set_markup("<i><small>%s</small></i>" % current_file)

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
				print "	 %s: %s" % (key, input_file[key])


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
			print "	 -%s arg, --%sarg" % (short[:1], long)
		else:
			print "	 -%s, --%s" % (short[:1], long)
		for line in textwrap.wrap(doc):
			print "	   %s" % line
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
