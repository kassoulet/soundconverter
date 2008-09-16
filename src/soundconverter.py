#!/usr/bin/python -tt
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats. 
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2008 Gautier Portet
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

NAME = "SoundConverter"
VERSION = "@version@"
GLADE = "@datadir@/soundconverter/soundconverter.glade"

print "%s %s" % (NAME, VERSION)

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
import unicodedata

# GNOME and related stuff.
try:
	import pygtk
	pygtk.require("2.0")
	import gtk
	import gtk.glade
	import gnome
	import gnome.ui
	import gconf
	import gobject
	gobject.threads_init()
	import gnomevfs
except ImportError:
	print "%s needs gnome-python 2.10!" % NAME
	sys.exit(1)

# only so I can test SC in my older boxes
if 'filename_display_name' not in dir(gobject):
	def __fake_display_name(name):
		return name
	gobject.filename_display_name = __fake_display_name

# GStreamer
try:
	# 0.10
	import pygst
	pygst.require('0.10')
	import gst
	
except ImportError:
	print "%s needs python-gstreamer 0.10!" % NAME
	sys.exit(1)

print "  using Gstreamer version: %s, Python binding version: %s" % (
		".".join([str(s) for s in gst.gst_version]), 
		".".join([str(s) for s in gst.pygst_version]) )

# This is missing from gst, for some reason.
FORMAT_PERCENT_SCALE = 10000

#localization
import locale
import gettext
PACKAGE = NAME.lower()
gettext.bindtextdomain(PACKAGE,"@datadir@/locale")
locale.setlocale(locale.LC_ALL,"")
gettext.textdomain(PACKAGE)
gettext.install(PACKAGE,localedir="@datadir@/locale",unicode=1)

gtk.glade.bindtextdomain(PACKAGE,"@datadir@/locale")
gtk.glade.textdomain(PACKAGE)

TRANSLATORS = ("""
Guillaume Bedot <littletux zarb.org> (French)
Dominik Zabłotny <dominz wp.pl> (Polish) 
Jonh Wendell <wendell bani.com.br> (Portuguese Brazilian)
Marc E. <m4rccd yahoo.com> (Spanish)
Daniel Nylander <po danielnylander se> (Swedish)
Alexandre Prokoudine <alexandre.prokoudine gmail.com> (Russian) 
Kamil Páral <ripper42 gmail.com > (Czech)
Stefano Luciani <luciani.fa tiscali.it > (Italian)
Martin Seifert <martinseifert fastmail.fm> (German)
Nizar Kerkeni <nizar.kerkeni gmail.com>(Arabic)
amenudo (Basque)
rainofchaos (Simplified Chinese)
Pavol Klačanský (Slovak)
Moshe Basanchig <moshe.basanchig gmail.com> (Hebrew)
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
	"application/x-3gp",
)

# custom filename patterns
english_patterns = "Artist Album Title Track Total Genre Date Year"

# traductors: These are the custom filename patterns. Only if it does make sense.
locale_patterns = _("Artist Album Title Track Total Genre Date Year")

patterns_formats = (
	"%(artist)s",
	"%(album)s",
	"%(title)s",
	"%(track-number)02d",
	"%(track-count)02d",
	"%(genre)s",
	"%(date)s",
	"%(year)s",
)

# add english and locale
custom_patterns = english_patterns + " " + locale_patterns
# convert to list
custom_patterns = [ "{%s}" % p for p in custom_patterns.split()]
# and finally to dict, thus removing doubles 
custom_patterns = dict(zip(custom_patterns, patterns_formats*2))

locale_patterns_dict = dict(zip(
	[ p.lower() for p in english_patterns.split()],
	[ "{%s}" % p for p in locale_patterns.split()] ))

# add here the formats not containing tags 
# not to bother searching in them
tag_blacklist = (
	"audio/x-wav",
)


# Name and pattern for CustomFileChooser
filepattern = (
	("All files","*.*"),
	("MP3","*.mp3"),
	("Ogg Vorbis","*.ogg"),
	("iTunes AAC ","*.m4a"),
	("Windows WAV","*.wav"),
	("AAC","*.aac"),
	("FLAC","*.flac"),
	("AC3","*.ac3")
)

def beautify_uri(uri):
	uri = unquote_filename(uri)
	if uri.startswith("file://"):
		return uri[7:]
	return uri

def vfs_walk(uri):
	"""similar to os.path.walk, but with gnomevfs.
	
	uri -- the base folder uri.
	return a list of uri.
	
	"""
	if str(uri)[-1] != '/':
		uri = uri.append_string("/")

	filelist = []  

	try:
		dirlist = gnomevfs.open_directory(uri)
	except:
		log(_("skipping: '%s'") % uri)
		return filelist
		
	for file_info in dirlist:
		try:
			if file_info.name[0] == ".":
				continue

			if file_info.type == gnomevfs.FILE_TYPE_DIRECTORY:
				filelist.extend(
					vfs_walk(uri.append_path(file_info.name)) )

			if file_info.type == gnomevfs.FILE_TYPE_REGULAR:
				filelist.append( str(uri.append_file_name(file_info.name)) )
		except ValueError:
			# this can happen when you do not have sufficent
			# permissions to read file info.
			log(_("skipping: '%s'") % uri)
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
		print folder
		uri = uri.append_string(folder.replace("%2f", "/"))
		try:
			gnomevfs.make_directory(uri, 0777)
		except gnomevfs.FileExistsError:
			pass
		except :
			return False
	return True  

def vfs_unlink(filename):
	gnomevfs.unlink(gnomevfs.URI(filename))

def vfs_exists(filename):
	try:
		return gnomevfs.exists(filename)
	except:
		return False

# GStreamer gnomevfssrc helpers

def vfs_encode_filename(filename):
	filename = filename.replace("%252f", "/")
	return filename

def file_encode_filename(filename):
	filename = gnomevfs.get_local_path_from_uri(filename)
	filename = filename.replace(" ", "\ ");
	filename = filename.replace("%2f", "/");
	return filename
	

def unquote_filename(filename):

	f= urllib.unquote(filename)
	return f


def format_tag(tag):
	if isinstance(tag, list):
		if len(tag) > 1:
			tag = ", ".join(tag[:-1]) + " & " + tag[-1]
		else:
			tag = tag[0]
			
	return tag

def markup_escape(message):
	return gobject.markup_escape_text(message)

def __filename_escape(str):
	str = str.replace("'","\'")
	str = str.replace("\"","\\\"")
	str = str.replace("!","\!")
	return str

required_elements = ("decodebin", "fakesink", "audioconvert", "typefind")
for element in required_elements:
	if not gst.element_factory_find(element):
		print "required gstreamer element '%s' not found." % element
		sys.exit(1)

use_gnomevfs = False

if gst.element_factory_find("giosrc"):
	gstreamer_source = "giosrc"
	gstreamer_sink = "giosink"
	encode_filename = vfs_encode_filename
	use_gnomevfs = True
	print "  using gio"
elif gst.element_factory_find("gnomevfssrc"):
	gstreamer_source = "gnomevfssrc"
	gstreamer_sink = "gnomevfssink"
	encode_filename = vfs_encode_filename
	use_gnomevfs = True
	print "  using deprecated gnomevfssrc"
else:
	gstreamer_source = "filesrc"
	gstreamer_sink = "filesink"
	encode_filename = file_encode_filename
	print "  not using gnomevfssrc, look for a gnomevfs gstreamer package."


encoders = ( 
	("flacenc",		"FLAC"), 
	("wavenc",		"WAV"),
	("vorbisenc",   "Ogg Vorbis"),
	("oggmux",		"Ogg Vorbis"),
	("id3v2mux",	"MP3 Tags"),
	("xingmux",		""),
	("lame",		"MP3"),
	("faac",        "AAC"))

for encoder, name in encoders:
	have_it = True
	if not gst.element_factory_find(encoder):
		have_it = False
		if name:
			print "  '%s' element not found, disabling %s." % (encoder, name)
	exec("have_%s = %s" % (encoder, have_it))

if not have_oggmux:
	have_vorbis = False

# logging & debugging  

def log(*args):
	if get_option("quiet") == False:
		print " ".join([str(msg) for msg in args])

def debug(*args):
	if get_option("debug") == True:
		print " ".join([str(msg) for msg in args])

def gtk_sleep(duration):
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
	"""Convert a filename to a valid uri.
	Filename can be a relative or absolute path, or an uri.
	"""
	if vfs_exists(filename):
		return str(gnomevfs.URI(filename))
	else:
		return "file://" + urllib.quote(os.path.abspath(filename))


class SoundFile:

	"""Meta data information about a sound file (uri, tags)."""

	#def __init__(self, base_path, filename=None):
	def __init__(self, uri, base_path=None):

		self.uri = uri

		if base_path:
			self.base_path = base_path
			self.filename = uri[len(base_path):]
		else:
			self.base_path, self.filename = os.path.split(self.uri)
			self.base_path += "/"
		self.filename_for_display = gobject.filename_display_name(
				unquote_filename(self.filename))
	
		self.tags = {
			"track-number": 0,
			"title":	"Unknown Title",
			"artist": "Unknown Artist",
			"album":	"Unknown Album",
		}
		self.have_tags = False
		self.tags_read = False
		self.duration = 0  
		self.mime_type = None 
		
	def get_uri(self):
		return self.uri
		
	def get_base_path(self):
		return self.base_path
		
	def get_filename(self):
		return self.filename
		
	def get_filename_for_display(self):
		return self.filename_for_display
		
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


class TargetNameGenerator:

	"""Generator for creating the target name from an input name."""

	nice_chars = string.ascii_letters + string.digits + ".-_/"

	def __init__(self):
		self.folder = None
		self.subfolders = ""
		self.basename= "%(.inputname)s"
		self.ext = "%(.ext)s"
		self.suffix = None
		self.replace_messy_chars = False
		self.max_tries = 2
		if use_gnomevfs:
			self.exists = gnomevfs.exists
		else:
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
		
	def _unicode_to_ascii(self, unicode_string):
		# thanks to http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/251871
		try:
			unicode_string = unicode(unicode_string, "utf-8")
			return unicodedata.normalize('NFKD', unicode_string).encode('ASCII', 'ignore')
		except UnicodeDecodeError:
			unicode_string = unicode(unicode_string, "iso-8859-1")
			return unicodedata.normalize('NFKD', unicode_string).encode('ASCII', 'replace')
			
	
	def get_target_name(self, sound_file):

		assert self.suffix, "you just forgot to call set_target_suffix()"

		u = gnomevfs.URI(sound_file.get_uri())
		root, ext = os.path.splitext(u.path)
		if u.host_port:
			host = "%s:%s" % (u.host_name, u.host_port)
		else:
			host = u.host_name
			
		root = sound_file.get_base_path()
		basename, ext = os.path.splitext(urllib.unquote(sound_file.get_filename()))
		
		dict = {
			".inputname": basename,
			".ext": ext,
			"album": "",
			"artist": "",
			"title": "",
			"track-number": 0,
			"track-count": 0,
			"genre": "",
			"year": "",
			"date": "",
		}
		for key in sound_file.keys():
			dict[key] = sound_file[key]
			if isinstance(dict[key], basestring):
				dict[key] = dict[key].replace("/", "-")
		
		pattern = os.path.join(self.subfolders, self.basename + self.suffix)
		result = pattern % dict
		if isinstance(result, unicode):
			result = result.encode('utf-8')
		if self.replace_messy_chars:
			result = self._unicode_to_ascii(result)
			s = ""
			for c in result:
				if c not in self.nice_chars:
					s += "_"
				else:
					s += c
			result = s

		if self.folder is None:
			folder = root
		else:
			folder = self.folder
		result = os.path.join(folder, urllib.quote(result))

		return result


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

	def show_exception(self, exception):
		self.show("<b>%s</b>" % markup_escape(exception.primary),
					exception.secondary)


class ErrorPrinter:

	def show(self, primary, secondary):
		sys.stderr.write(_("\n\nError: %s\n%s\n") % (primary, secondary))
		sys.exit(1)

	def show_exception(self, e):
		self.show(e.primary, e.secondary)


error = None

_thread_sleep = 0.1
#_thread_method = "thread"
#_thread_method = "idle"
_thread_method = "timer"

class BackgroundTask:

	"""A background task.
	
	To use: derive a subclass and define the methods setup, work, and
	finish. Then call the run method when you want to start the task.
	Call the stop method if you want to stop the task before it finishes
	normally."""

	def __init__(self):
		self.paused = False
		self.current_paused_time = 0

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

		if _thread_method == "timer":
			self.id = gobject.timeout_add( int(_thread_sleep*1000), self.do_work) 
		elif _thread_method == "idle":
			self.id = gobject.idle_add(self.do_work)
		else:
			thread.start_new_thread(self.thread_work, ())

	def thread_work(self):
		working = True
		while self and working:
			working = self.do_work_()
			sleep(_thread_sleep)
			while gtk.events_pending():
				gtk.main_iteration()


	def do_work(self):
		working = self.do_work_()
		return working


	def do_work_(self):
		"""Do some work by calling work(). Call finish() if work is done."""
		try:
			if _thread_method == "idle":
				time.sleep(_thread_sleep)
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
				self._run = False
				self = None
				return False
		except SoundConverterException, e:
			self._run = False
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
		BackgroundTask.__init__(self)
		self.tasks = []
		self.all_tasks = []
		self.running = None
		self.tasks_done = 0
		self.tasks_number = 0

	def is_running(self):
		if self.running:
			return True
		return False

	def add(self, task):
		#print 'adding task:', task
		self.tasks.append(task)
		self.all_tasks.append(task)
		self.tasks_number += 1
		
	def get_current_task(self):
		if self.running:
			return self.running[0]
		else:
			return None

	def start_next_task(self):
		#print 'start next tasks:'
		#self.running = []
		to_start = get_option('jobs') - len(self.running)
		#print 'trying to start:', to_start
		for i in range(to_start):
			try:
				task = self.tasks.pop()
			except IndexError:
				return
			self.running.append(task)
			task.setup()

	def setup(self):
		""" BackgroundTask setup callback """
		self.running = []
		self.start_time = time.time()
		self.tasks_done = 0

		self.start_next_task()
		if self.running:
			[self.setup_hook(task) for task in self.running]

			
	def work(self):
		""" BackgroundTask work callback """
		if self.running:
			self.work_hook(self.running)
			for task in self.running:
				ret = task.work()
				if not ret:
					self.tasks_done += 1
					self.finish_hook(task)
					task.finish()
					self.running.remove(task)
					self.start_next_task()
			return True
		return False

	def finish(self):
		""" BackgroundTask finish callback """
		self.running = None 
		log("Queue done in %ds" % (time.time() - self.start_time))
		self.queue_ended()
		self.tasks_number = 0


	def stop(self):
		if self.running:
			[task.stop() for task in self.running]
		BackgroundTask.stop(self)
		self.running = None
		self.tasks = []
		self.tasks_number = 0

	# The following hooks are called after each sub-task has been set up,
	# after its work method has been called, and after it has finished.
	# Subclasses may override these to provide additional processing.

	def setup_hook(self, task):
		pass
		
	def work_hook(self, task):
		pass
		
	def finish_hook(self, task):
		pass

	# The following is called when the Queue is finished
	def queue_ended(self):
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
		BackgroundTask.__init__(self)
		self.pipeline = None #gst.Pipeline()
		self.command = ""
		self.parsed = False
		self.signals = []
		self.processing = False
		self.eos = False
		self.error = None
		
	def setup(self):
		#print "Pipeline.setup()"
		self.play()
	
	def work(self):
		if self.eos:
			return False
		return True

	def finish(self):
		#print "Pipeline.finish()"
		self.stop_pipeline()

	def add_command(self, command):
		if self.command:
			self.command += " ! "
		self.command += command

	def add_signal(self, name, signal, callback):
		self.signals.append( (name, signal, callback,) )

	def toggle_pause(self, paused):
		if not self.pipeline:
			debug("toggle_pause(): pipeline is None !")
			return

		if paused:
			self.pipeline.set_state(gst.STATE_PAUSED)
		else:
			self.pipeline.set_state(gst.STATE_PLAYING)

	def found_tag(self, decoder, something, taglist):
		pass
		
	def install_plugin_cb(self, result):
		if result == gst.pbutils.INSTALL_PLUGINS_SUCCESS:
			gst.update_registry()
			self.parsed = False
			self.play()
			return
		self.finish()
		if result == gst.pbutils.INSTALL_PLUGINS_USER_ABORT:
			dialog = gtk.MessageDialog(parent=None, flags=gtk.DIALOG_MODAL, 
				type=gtk.MESSAGE_INFO, 
				buttons=gtk.BUTTONS_OK, 
				message_format="Plugin installation aborted.")
			dialog.run()
			dialog.hide()
			return

		error.show("Error", "failed to install plugins: %s" % markup_escape(str(result)))
		
	def on_message(self, bus, message):
		t = message.type
		import gst
		if t == gst.MESSAGE_ERROR:
			err, debug = message.parse_error()
			self.eos = True
			self.error = err
			log("error: %s (%s)" % (err,
				self.sound_file.get_filename_for_display()))
				
		elif t == gst.MESSAGE_ELEMENT:
			st = message.structure
			if st and st.get_name().startswith('missing-'):
				self.pipeline.set_state(gst.STATE_NULL)
				if gst.pygst_version >= (0, 10, 10):
					import gst.pbutils
					detail = gst.pbutils.missing_plugin_message_get_installer_detail(message)
					ctx = gst.pbutils.InstallPluginsContext()
					gst.pbutils.install_plugins_async([detail], ctx, self.install_plugin_cb)
			#error.show("GStreamer Error", "%s\nfile: '%s'" % (err, 
			#	self.sound_file.get_filename_for_display()))
		elif t == gst.MESSAGE_EOS:
			self.eos = True
		elif t == gst.MESSAGE_TAG:
			self.found_tag(self, "", message.parse_tag())  
		return True

	def play(self):
		if not self.parsed:
			debug("launching: '%s'" % self.command)
			try:
				self.pipeline = gst.parse_launch(self.command)
				bus = self.pipeline.get_bus()
				for name, signal, callback in self.signals:
					if name:
						self.pipeline.get_by_name(name).connect(signal,callback)
					else:
						bus.connect(signal,callback)
				self.parsed = True
			except gobject.GError, e:
				error.show("GStreamer error when creating pipeline", str(e))
				self.eos = True # TODO
				return

		bus.add_signal_watch()
		watch_id = bus.connect('message', self.on_message)
		self.watch_id = watch_id
	
		self.pipeline.set_state(gst.STATE_PLAYING)

	def stop_pipeline(self):
		if not self.pipeline:
			debug("pipeline already stopped!")
			return
		bus = self.pipeline.get_bus()
		bus.disconnect(self.watch_id)
		bus.remove_signal_watch()
		self.pipeline.set_state(gst.STATE_NULL)
		self.pipeline = None
		del self.watch_id

	def get_position(self):
		return 0

class TypeFinder(Pipeline):
	def __init__(self, sound_file):
		Pipeline.__init__(self)
		self.sound_file = sound_file
	
		command = '%s location="%s" ! typefind name=typefinder ! fakesink' % \
			(gstreamer_source, encode_filename(self.sound_file.get_uri()))
		self.add_command(command)
		self.add_signal("typefinder", "have-type", self.have_type)

	def set_found_type_hook(self, found_type_hook):
		self.found_type_hook = found_type_hook
	
	def have_type(self, typefind, probability, caps):
		mime_type = caps.to_string()
		#debug("have_type:", mime_type, self.sound_file.get_filename_for_display())
		self.sound_file.mime_type = None
		#self.sound_file.mime_type = mime_type
		for t in mime_whitelist:
			if t in mime_type:
				self.sound_file.mime_type = mime_type
		if not self.sound_file.mime_type:
			log("Mime type skipped: %s" % mime_type)
	
	def work(self):
		return Pipeline.work(self) and not self.sound_file.mime_type

	def finish(self):
		Pipeline.finish(self)
		if self.found_type_hook and self.sound_file.mime_type:
			gobject.idle_add(self.found_type_hook, self.sound_file, self.sound_file.mime_type)


class Decoder(Pipeline):

	"""A GstPipeline background task that decodes data and finds tags."""

	def __init__(self, sound_file):
		#print "Decoder()"
		Pipeline.__init__(self)
		self.sound_file = sound_file
		self.time = 0
		self.position = 0
		
		command = '%s location="%s" name=src ! decodebin name=decoder' % \
			(gstreamer_source, encode_filename(self.sound_file.get_uri()))
		self.add_command(command)
		self.add_signal("decoder", "new-decoded-pad", self.new_decoded_pad)

		# TODO add error management

	def have_type(self, typefind, probability, caps):
		pass

	def query_duration(self):
		try:
			if not self.sound_file.duration:
				self.sound_file.duration = self.pipeline.query_duration(gst.FORMAT_TIME)[0] / gst.SECOND
				debug("got file duration:", self.sound_file.duration)
		except gst.QueryError:
			pass

	def found_tag(self, decoder, something, taglist):
		pass

	def _buffer_probe(self, pad, buffer):
		"""buffer probe callback used to get real time since the beginning of the stream"""
		if buffer.timestamp == gst.CLOCK_TIME_NONE:
			debug("removing buffer probe")
			pad.remove_buffer_probe(self.probe_id)
			return False

		#if time.time() > self.time + 0.1:
		#	self.time = time.time()
		self.position = float(buffer.timestamp) / gst.SECOND

		return True
	
	def new_decoded_pad(self, decoder, pad, is_last):
		""" called when a decoded pad is created """
		self.probe_id = pad.add_buffer_probe(self._buffer_probe)
		self.processing = True
		self.query_duration()

	def get_sound_file(self):
		return self.sound_file

	def get_input_uri(self):
		return self.sound_file.get_uri()

	def get_duration(self):
		""" return the total duration of the sound file """
		#if not self.pipeline:
		#  return 0
		self.query_duration()
		return self.sound_file.duration
	
	def get_position(self):
		""" return the current pipeline position in the stream """
		return self.position

class TagReader(Decoder):

	"""A GstPipeline background task for finding meta tags in a file."""

	def __init__(self, sound_file):
		Decoder.__init__(self, sound_file)
		self.found_tag_hook = None
		self.found_tags = False
		self.run_start_time = 0 
		self.add_command("fakesink")
		self.add_signal(None, "message::state-changed", self.on_state_changed)

	def set_found_tag_hook(self, found_tag_hook):
		self.found_tag_hook = found_tag_hook

	def on_state_changed(self, bus, message):
		prev, new, pending = message.parse_state_changed()
		if new == gst.STATE_PLAYING:
			debug("TagReading done...")
			self.finish()

	def found_tag(self, decoder, something, taglist):
		#debug("found_tags:", self.sound_file.get_filename_for_display())
		#debug("\ttitle=%s" % (taglist["title"]))
		"""for k in taglist.keys():
			debug("\t%s=%s" % (k, taglist[k]))
			if isinstance(taglist[k], gst.Date):
				taglist["year"] = taglist[k].year
				taglist["date"] = "%04d-%02d-%02d" % (taglist[k].year,
									taglist[k].month, taglist[k].day)"""
			
		self.sound_file.add_tags(taglist)

		#self.found_tags = True
		self.sound_file.have_tags = True

		try:
			self.sound_file.duration = self.pipeline.query_duration(gst.FORMAT_TIME)[0] / gst.SECOND
		except gst.QueryError:
			pass

	def work(self):
		if not self.pipeline:
			return False
		
		if not self.run_start_time:
			if self.sound_file.mime_type in tag_blacklist:
				log("%s: type is %s, tag reading blacklisted" % (self.sound_file.get_filename_for_display(), self.sound_file.mime_type))
				return False
			self.run_start_time = time.time()
			
		if self.pipeline.get_state() != gst.STATE_PLAYING:
			self.run_start_time = time.time()

		if time.time()-self.run_start_time > 5:
			# stop looking for tags after 5s 
			return False
		return Decoder.work(self) and not self.found_tags

	def finish(self):
		Pipeline.finish(self)
		self.sound_file.tags_read = True
		if self.found_tag_hook:
			gobject.idle_add(self.found_tag_hook, self)


class ConversionTargetExists(SoundConverterException):

	def __init__(self, uri):
		SoundConverterException.__init__(self, _("Target exists."),
										 (_("The output file %s already exists.")) % uri)


class Converter(Decoder):

	"""A background task for converting files to another format."""

	def __init__(self, sound_file, output_filename, output_type, delete_original=False, output_resample=False, resample_rate=48000):
		#print "Converter()"
		Decoder.__init__(self, sound_file)

		self.converting = True
		
		self.output_filename = output_filename
		self.output_type = output_type
		self.vorbis_quality = None
		self.mp3_bitrate = None
		self.mp3_mode = None
		self.mp3_quality = None

		self.output_resample = output_resample
		self.resample_rate = resample_rate

		self.overwrite = False
		self.delete_original = delete_original

	#def setup(self):
	#  self.init()
	#  self.play()

	def init(self):
		#print "Converter.init()"
		self.encoders = {
			"audio/x-vorbis": self.add_oggvorbis_encoder,
			"audio/x-flac": self.add_flac_encoder,
			"audio/x-wav": self.add_wav_encoder,
			"audio/mpeg": self.add_mp3_encoder,
			"audio/x-m4a": self.add_aac_encoder,
		}

		self.add_command("audioconvert")
		#TODO self.add_command("audioscale")

		#Hacked in audio resampling support
		if self.output_resample:
			#print "Resampling to %dHz" % (self.resample_rate)
			self.add_command("audioresample ! audio/x-raw-float,rate=%d" % 
					 (self.resample_rate))
			self.add_command("audioconvert")
		
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
	
		self.add_command('%s location=%s' % (
			gstreamer_sink, encode_filename(self.output_filename)))
		if self.overwrite and vfs_exists(self.output_filename):
			log("overwriting '%s'" % self.output_filename)
			vfs_unlink(self.output_filename)
		#log( _("Writing to: '%s'") % urllib.unquote(self.output_filename) )

	def finish(self):
		self.converting = False
		Pipeline.finish(self)
		
		# Copy file permissions
		try:
			info = gnomevfs.get_file_info( self.sound_file.get_uri(),gnomevfs.FILE_INFO_FIELDS_PERMISSIONS)
			gnomevfs.set_file_info(self.output_filename, info, gnomevfs.SET_FILE_INFO_PERMISSIONS)
		except:
			log(_("Cannot set permission on '%s'") % gnomevfs.format_uri_for_display(self.output_filename))

		if self.delete_original and self.processing and not self.error:
			log("deleting: '%s'" % self.sound_file.get_uri())
			gnomevfs.unlink(self.sound_file.get_uri())

	def get_position(self):
		return self.position
	
	def set_vorbis_quality(self, quality):
		self.vorbis_quality = quality

	def set_mp3_mode(self, mode):
		self.mp3_mode = mode

	def set_mp3_quality(self, quality):
		self.mp3_quality = quality

	def add_flac_encoder(self):
		s = "flacenc mid-side-stereo=true quality=8"
		return s

	def add_wav_encoder(self):
		return "wavenc"

	def add_oggvorbis_encoder(self):
		cmd = "vorbisenc"
		if self.vorbis_quality is not None:
			cmd += " quality=%s" % self.vorbis_quality
		cmd += " ! oggmux "
		return cmd

	def add_mp3_encoder(self):
	
		cmd = "lame quality=2 "
		
		if self.mp3_mode is not None:
			properties = {
				"cbr" : (0,"bitrate"),
				"abr" : (3,"vbr-mean-bitrate"),
				"vbr" : (4,"vbr-quality")
			}

			cmd += "vbr=%s " % properties[self.mp3_mode][0]
			if self.mp3_quality == 9:
				# GStreamer set max bitrate to 320 but lame uses
				# mpeg2 with vbr-quality==9, so max bitrate is 160
				# - update: now set to 128 since lame don't accept 160 anymore.
				cmd += "vbr-max-bitrate=128 "
			
			cmd += "%s=%s " % (properties[self.mp3_mode][1], self.mp3_quality)
	
			if have_xingmux and properties[self.mp3_mode][0]:
				# add xing header when creating VBR mp3
				cmd += "! xingmux "
			
		if have_id3v2mux:
			# add tags
			cmd += "! id3v2mux "
		
		return cmd

	def add_aac_encoder(self):
		return "faac profile=2 ! ffmux_mp4"

class FileList:
	"""List of files added by the user."""

	# List of MIME types which we accept for drops.
	drop_mime_types = ["text/uri-list", "text/plain", "STRING"]

	def __init__(self, window, glade):
		self.window = window
		self.tagreaders  = TaskQueue()
		self.typefinders = TaskQueue()
		# handle the current task for status

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
			file_list = []
			self.add_uris([uri.strip() for uri in selection.data.split("\n")])
			context.finish(True, False, time)

	def get_files(self):
		files = []
		i = self.model.get_iter_first()
		while i:
			f = {}
			for c in ALL_COLUMNS:
				f[c] = self.model.get_value(i, ALL_COLUMNS.index(c))
			files.append(f["META"])

			i = self.model.iter_next(i)
		return files
	
	def found_type(self, sound_file, mime):
		debug("found_type", sound_file.get_filename())

		self.append_file(sound_file)
		self.window.set_sensitive()

		tagreader = TagReader(sound_file)
		tagreader.set_found_tag_hook(self.append_file_tags)

		self.tagreaders.add(tagreader)
		if not self.tagreaders.is_running():
			self.tagreaders.run()
	
	def add_uris(self, uris, base=None, filter=None):

		files = []
		
		for uri in uris:
			if uri.startswith('cdda:'):
				error.show("Cannot read from Audio CD.",
					"Use SoundJuicer Audio CD Extractor instead.")
				return
			try:
				info = gnomevfs.get_file_info(gnomevfs.URI(uri))
			except gnomevfs.NotFoundError:
				log('uri not found: \'%s\'' % uri)
				continue
			except gnomevfs.InvalidURIError:
				log('unvalid uri: \'%s\'' % uri)
				continue
			except gnomevfs.AccessDeniedError:
				log('access denied: \'%s\'' % uri)
				continue
			except TypeError, e:
				log('error: %s (%s)' % (e, uri))
				continue
			except :
				log('error in get_file_info: %s' % (uri))
				continue

			if info.type == gnomevfs.FILE_TYPE_DIRECTORY:
				filelist = vfs_walk(gnomevfs.URI(uri))
				if filter:
					filelist = [f for f in filelist if f.lower().endswith(filter)]
				
				for f in filelist:
					files.append(f)
			else:
				files.append(uri)
				
		base,notused = os.path.split(os.path.commonprefix(files))
		base += "/"

		for f in files:
			sound_file = SoundFile(f, base)
			if sound_file.get_uri() in self.filelist:
				log(_("file already present: '%s'") % sound_file.get_uri())
				continue 
			self.filelist[sound_file.get_uri()] = True

			#self.found_type(sound_file, "test")
			typefinder = TypeFinder(sound_file)
			typefinder.set_found_type_hook(self.found_type)
			self.typefinders.add(typefinder)

		if files and not self.typefinders.is_running():
			self.typefinders.queue_ended = self.typefinder_queue_ended
			self.typefinders.run()

	def typefinder_queue_ended(self):
		pass

	def format_cell(self, sound_file):
		
		template_tags		 = "%(artist)s - <i>%(album)s</i> - <b>%(title)s</b>\n<small>%(filename)s</small>"
		template_loading = "<i>%s</i>\n<small>%%(filename)s</small>" \
							% _("loading tags...")
		template_notags  = '<span foreground="red">%s</span>\n<small>%%(filename)s</small>' \
							% _("no tags")

		params = {}
		params["filename"] = markup_escape(unquote_filename(sound_file.get_filename()))
		for item in ("title", "artist", "album"):
			params[item] = markup_escape(format_tag(sound_file.get_tag(item)))
		if sound_file["bitrate"]:
			params["bitrate"] = ", %s kbps" % (sound_file["bitrate"] / 1000)
		else:
			params["bitrate"] = ""


		if sound_file.have_tags:
			template = template_tags
		else:
			if sound_file.tags_read:
				template = template_notags
			else:
				template = template_loading

		s = template % params
			
		return s

	def append_file(self, sound_file):

		iter = self.model.append([self.format_cell(sound_file), sound_file])
		self.window.progressbar.pulse()
			
	
	def append_file_tags(self, tagreader):
		sound_file = tagreader.get_sound_file()

		fields = {}
		for key in ALL_COLUMNS:
			fields[key] = _("unknown")
		fields["META"] = sound_file
		fields["filename"] = sound_file.get_filename_for_display()

		# TODO: SLOW!
		for i in self.model:
			if i[1] == sound_file:
				i[0] = self.format_cell(sound_file)
		self.window.set_sensitive()
		self.window.progressbar.pulse()

	def remove(self, iter):
		uri = self.model.get(iter, 1)[0].get_uri()
		del self.filelist[uri]
		self.model.remove(iter)
		
	def is_nonempty(self):
		try:
			self.model.get_iter((0,))
		except ValueError:
			return False
		return True


class PreferencesDialog:

	root = "/apps/SoundConverter"
	
	basename_patterns = [
		("%(.inputname)s", _("Same as input, but replacing the suffix")),
		("%(.inputname)s%(.ext)s", _("Same as input, but with an additional suffix")),
		("%(track-number)02d-%(title)s", _("Track number - title")),
		("%(title)s", _("Track title")),
		("%(artist)s-%(title)s", _("Artist - title")),
		("Custom", _("Custom filename pattern")),
	]
	
	subfolder_patterns = [
		("%(artist)s/%(album)s", _("artist/album")),
		("%(artist)s-%(album)s", _("artist-album")),
		("%(artist)s - %(album)s", _("artist - album")),
	]
	
	defaults = {
		"same-folder-as-input": 1,
		"selected-folder": os.path.expanduser("~"),
		"create-subfolders": 0,
		"subfolder-pattern-index": 0,
		"name-pattern-index": 0,
		"custom-filename-pattern": "{Track} - {Title}",
		"replace-messy-chars": 0,
		"output-mime-type": "audio/x-vorbis",
		"output-suffix": ".ogg",
		"vorbis-quality": 0.6,
		"mp3-mode": "vbr",			# 0: cbr, 1: abr, 2: vbr
		"mp3-cbr-quality": 192,
		"mp3-abr-quality": 192,
		"mp3-vbr-quality": 3,
		"delete-original": 0,
		"output-resample": 0,
		"resample-rate": 48000,
		"flac-speed": 0,
	}

	sensitive_names = ["vorbis_quality", "choose_folder", "create_subfolders",
						 "subfolder_pattern"]

	def __init__(self, glade):
		self.gconf = gconf.client_get_default()
		self.gconf.add_dir(self.root, gconf.CLIENT_PRELOAD_ONELEVEL)
		self.dialog = glade.get_widget("prefsdialog")
		self.into_selected_folder = glade.get_widget("into_selected_folder")
		self.target_folder_chooser = glade.get_widget("target_folder_chooser")
		self.basename_pattern = glade.get_widget("basename_pattern")
		self.custom_filename_box = glade.get_widget("custom_filename_box")
		self.custom_filename = glade.get_widget("custom_filename")
		self.example = glade.get_widget("example_filename")
		self.aprox_bitrate = glade.get_widget("aprox_bitrate")
		self.quality_tabs = glade.get_widget("quality_tabs")
		self.delete_original = glade.get_widget("delete_original")
		self.resample_toggle = glade.get_widget("resample_toggle")
		self.resample_rate = glade.get_widget("resample_rate")

		self.target_bitrate = None
		self.convert_setting_from_old_version()
		
		self.sensitive_widgets = {}
		for name in self.sensitive_names:
			self.sensitive_widgets[name] = glade.get_widget(name)
			assert self.sensitive_widgets[name] != None
		self.set_widget_initial_values(glade)
		self.set_sensitive()

		tips = gtk.Tooltips()
		tip = _("Available patterns:")
		for k in locale_patterns_dict.values():
			tip += "\n" + k
		tips.set_tip(self.custom_filename, tip)


	def convert_setting_from_old_version(self):
		""" try to convert previous settings"""
		
		# vorbis quality was once stored as an int enum
		try:
			self.get_float("vorbis-quality")
		except gobject.GError:
			log("deleting old settings...")
			[self.gconf.unset(self.path(k)) for k in self.defaults.keys()]

		self.gconf.clear_cache()

	def set_widget_initial_values(self, glade):
		
		self.quality_tabs.set_show_tabs(False)
		
		if self.get_int("same-folder-as-input"):
			w = glade.get_widget("same_folder_as_input")
		else:
			w = glade.get_widget("into_selected_folder")
		w.set_active(True)
		
		uri = filename_to_uri(self.get_string("selected-folder"))
		self.target_folder_chooser.set_uri(uri)
		self.update_selected_folder()
	
		w = glade.get_widget("create_subfolders")
		w.set_active(self.get_int("create-subfolders"))
		
		w = glade.get_widget("subfolder_pattern")
		model = w.get_model()
		model.clear()
		for pattern, desc in self.subfolder_patterns:
			i = model.append()
			model.set(i, 0, desc)
		w.set_active(self.get_int("subfolder-pattern-index"))

		if self.get_int("replace-messy-chars"):
			w = glade.get_widget("replace_messy_chars")
			w.set_active(True)

		if self.get_int("delete-original"):
			self.delete_original.set_active(True)

		mime_type = self.get_string("output-mime-type")

		widgets = (	("audio/x-vorbis", have_vorbisenc),
					("audio/mpeg"    , have_lame),
					("audio/x-flac"  , have_flacenc),
					("audio/x-wav"   , have_wavenc),
					("audio/x-m4a"   , have_faac),
					)

		# desactivate output if encoder plugin is not present
		widget = glade.get_widget('output_mime_type')
		model = widget.get_model()
		self.present_mime_types = []
		for i, b in enumerate(widgets):
			mime, encoder_present = b
			if not encoder_present:
				del model[i]
				if mime_type == mime:
					mime_type = self.defaults["output-mime-type"]
			else:
				self.present_mime_types.append(mime)
		for i, mime in enumerate(self.present_mime_types):
			if mime_type == mime:
				widget.set_active(i)
		self.change_mime_type(mime_type)
		
		# display information about mp3 encoding
		if not have_lame:
			w = glade.get_widget("lame_absent")
			w.show()
			
		w = glade.get_widget("vorbis_quality")
		quality = self.get_float("vorbis-quality")
		quality_setting = {0:0 ,0.2:1 ,0.4:2 ,0.6:3 , 0.8:4, 1.0:5}
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
		
		self.custom_filename.set_text(self.get_string("custom-filename-pattern"))
		if self.basename_pattern.get_active() == len(self.basename_patterns)-1:
			self.custom_filename_box.set_sensitive(True)
		else:
			self.custom_filename_box.set_sensitive(False)

		if self.get_int("output-resample"):
			self.resample_toggle.set_active(self.get_int("output-resample"))
			self.resample_rate.set_sensitive(1)
			rr_entry = glade.get_widget("resample_rate-entry")
			rr_entry.set_text("%d" % (self.get_int("resample-rate")))

		self.update_example()

	def update_selected_folder(self):
		self.into_selected_folder.set_label(_("Into folder %s") % 
			beautify_uri(self.get_string("selected-folder")))


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
			"track-number": 1L,
			"track-count": 99L,
		})
		sound_file.add_tags(locale_patterns_dict)

		s = markup_escape(self.generate_filename(sound_file, for_display=True))
		p = 0
		replaces = []

		while 1:
			b = s.find('{', p)
			if b == -1:
				break
			e = s.find('}',b)
			
			tag = s[b:e+1]
			if tag.lower() in [v.lower() for v in locale_patterns_dict.values()]:
				k = tag
				l = k.replace("{","<b>{")
				l = l.replace("}","}</b>")
				replaces.append([k,l])
			else:
				k = tag
				l = k.replace("{","<span foreground=\"red\"><i>{")
				l = l.replace("}","}</i></span>")
				replaces.append([k,l])
			p = b+1
			
		for k,l in replaces:
			s = s.replace(k, l)

		self.example.set_markup(s)
		
		markup = "<small>%s</small>" % (_("Target bitrate: %s") % 
					self.get_bitrate_from_settings())
		self.aprox_bitrate.set_markup( markup )

	def generate_filename(self, sound_file, for_display=False):
		self.gconf.clear_cache()
		output_type = self.get_string("output-mime-type")
		output_suffix = {
						"audio/x-vorbis": ".ogg",
						"audio/x-flac": ".flac",
						"audio/x-wav": ".wav",
						"audio/mpeg": ".mp3",
                        "audio/x-m4a": ".m4a",
					}.get(output_type, None)

		generator = TargetNameGenerator()

		generator.set_target_suffix(output_suffix)
		if not self.get_int("same-folder-as-input"):
			generator.set_folder(self.get_string("selected-folder"))
		if self.get_int("create-subfolders"):
			generator.set_subfolder_pattern(
				self.get_subfolder_pattern())
		generator.set_basename_pattern(self.get_basename_pattern())
		if for_display:
			generator.set_replace_messy_chars(False)
			return unquote_filename(generator.get_target_name(sound_file))
		else:
			generator.set_replace_messy_chars(
				self.get_int("replace-messy-chars"))
			return generator.get_target_name(sound_file)
	
	def process_custom_pattern(self, pattern):
		
		for k in custom_patterns:
			pattern = pattern.replace(k, custom_patterns[k])
		return pattern

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

	def on_delete_original_toggled(self, button):
		if button.get_active():
			self.set_int("delete-original", 1)
		else:
			self.set_int("delete-original", 0)
			
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
			folder = self.target_folder_chooser.get_uri()
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
		if combobox.get_active() == len(self.basename_patterns)-1:
			self.custom_filename_box.set_sensitive(True)
		else:
			self.custom_filename_box.set_sensitive(False)
		self.update_example()

	def get_basename_pattern(self):
		index = self.get_int("name-pattern-index")
		if index < 0 or index >= len(self.basename_patterns):
			index = 0
		if self.basename_pattern.get_active() == len(self.basename_patterns)-1:
			return self.process_custom_pattern(self.custom_filename.get_text())
		else:
			return self.basename_patterns[index][0]
	
	def on_custom_filename_changed(self, entry):
		self.set_string("custom-filename-pattern", entry.get_text())
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
						"audio/x-m4a": 3,
		}
		self.quality_tabs.set_current_page(tabs[mime_type])

	def on_output_mime_type_changed(self, combo):
		self.change_mime_type(
			self.present_mime_types[combo.get_active()]
		)

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

	def on_output_mime_type_aac_toggled(self, button):
		if button.get_active():
			self.change_mime_type("audio/x-m4a")

	def on_vorbis_quality_changed(self, combobox):
		quality = (0,0.2,0.4,0.6,0.8,1.0)
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
			"cbr": {64:0, 96:1, 128:2, 192:3, 256:4, 320:5},
			"abr": {64:0, 96:1, 128:2, 192:3, 256:4, 320:5},
			"vbr": {9:0,   7:1,   5:2,   3:3,   1:4,   0:5}, # inverted !
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
			"cbr": (64, 96, 128, 192, 256, 320),
			"abr": (64, 96, 128, 192, 256, 320),
			"vbr": (9, 7, 5, 3, 1, 0),
		}
		mode = self.get_string("mp3-mode")
		self.set_int(keys[mode], quality[mode][combobox.get_active()])

		self.update_example()

	def on_resample_rate_changed(self, combobox):
		changeto = combobox.get_active_text()
		if int(changeto) >= 2:
			self.set_int("resample-rate", int(changeto))

	def on_resample_toggle(self, rstoggle):
		self.set_int("output-resample", rstoggle.get_active())
		self.resample_rate.set_sensitive(rstoggle.get_active())


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
		self.total_duration = 0
		self.duration_processed = 0
		self.overwrite_action = None

	def add(self, sound_file):
	
		output_filename = self.window.prefs.generate_filename(sound_file)
		path = urlparse.urlparse(output_filename) [2]
		path = unquote_filename(path)
	
		exists = True
		try:
			gnomevfs.get_file_info(gnomevfs.URI((output_filename)))
		except gnomevfs.NotFoundError:
			exists = False
		except :
			log("Invalid URI: '%s'" % output_filename)
			return
		
		# do not overwrite source file !!
		if output_filename == sound_file.get_uri():
			error.show(_("Cannot overwrite source file(s)!"), "")
			raise ConverterQueueCanceled()
		
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
					vfs_unlink(output_filename)
				except gnomevfs.NotFoundError:
					pass
			elif result == 0: 
				# skip file
				return
			else:
				# cancel operation
				# TODO
				raise ConverterQueueCanceled()
			
		c = Converter(sound_file, output_filename, 
			                        self.window.prefs.get_string("output-mime-type"),
			                        self.window.prefs.get_int("delete-original"),
			                        self.window.prefs.get_int("output-resample"),
			                        self.window.prefs.get_int("resample-rate"))
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
		c.got_duration = False
		#self.total_duration += c.get_duration()

	def work_hook(self, tasks):
		gobject.idle_add(self.set_progress, (tasks))

	def get_progress(self, task):
		return (self.duration_processed + task.get_position()) / self.total_duration

	def set_progress(self, tasks):
		filename = ""
		if tasks and tasks[0]:
			filename = tasks[0].sound_file.get_filename_for_display()

		# try to get all tasks durations
		total_duration = self.total_duration
		for task in self.all_tasks:
			if not task.got_duration:
				duration = task.sound_file.duration
				if duration: 
					self.total_duration += duration
					task.got_duration = True
				else:
					total_duration = 0 

		position = 0
		for task in tasks:
			if task.converting :
				position += task.get_position()

		#print self.duration_processed, position, total_duration
		self.window.set_progress(self.duration_processed + position,
							 total_duration, filename)
		return False

	def finish_hook(self, task):
		self.duration_processed += task.get_duration()

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
		self.reset_counters()

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
		self.fcw.set_local_only(not use_gnomevfs)
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
		for name, pattern in filepattern:
			self.add_pattern(name,pattern)
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
		

	def filter_cb(self, info, pattern):
		filename = info[2]
		return filename.lower().endswith(pattern[1:])

	def on_combo_changed(self,w):
		"""
		Callback for combobox "changed" signal\n
		Set a new filter for the filechooserwidget
		"""
		filter = gtk.FileFilter()
		active = self.combo.get_active()
		if active:
			filter.add_custom(gtk.FILE_FILTER_DISPLAY_NAME, self.filter_cb, self.pattern[self.combo.get_active()])
		else:
			filter.add_pattern('*.*')
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

	sensitive_names = [ "remove", "clear", "toolbutton_clearlist", "convert_button" ]
	unsensitive_when_converting = [ "remove", "clear", "prefs_button" ,"toolbutton_addfile", "toolbutton_addfolder", "toolbutton_clearlist", "filelist", "menubar" ]

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

		self.progressframe = glade.get_widget("progress_frame")
		self.statusframe = glade.get_widget("status_frame")
		self.progressfile = glade.get_widget("progressfile")

		self.addchooser = CustomFileChooser()
		self.addfolderchooser = gtk.FileChooserDialog(_("Add Folder..."),
												self.widget,
												gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
												(gtk.STOCK_CANCEL, 
													gtk.RESPONSE_CANCEL,
													gtk.STOCK_OPEN,
													gtk.RESPONSE_OK))
		self.addfolderchooser.set_select_multiple(True)
		self.addfolderchooser.set_local_only(not use_gnomevfs)


		self.combo = gtk.ComboBox()
		#self.combo.connect("changed",self.on_combo_changed)
		self.store = gtk.ListStore(str)
		self.combo.set_model(self.store)
		combo_rend = gtk.CellRendererText()
		self.combo.pack_start(combo_rend, True)
		self.combo.add_attribute(combo_rend, 'text', 0)
	
		# get all (gstreamer) knew files Todo
		for files in filepattern:
			self.store.append(["%s (%s)" %(files[0],files[1])])

		self.combo.set_active(0)
		self.addfolderchooser.set_extra_widget(self.combo)

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

		self.set_status()

	# This bit of code constructs a list of methods for binding to Gtk+
	# signals. This way, we don't have to maintain a list manually,
	# saving editing effort. It's enough to add a method to the suitable
	# class and give the same name in the .glade file.
	
	def connect(self, glade, objects):
		dicts = {}
		for o in [self] + objects:
			for name, member in inspect.getmembers(o):
				dicts[name] = member
		glade.signal_autoconnect(dicts)

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
			self.filelist.add_uris(self.addchooser.get_uris())
		self.set_sensitive()


	def on_addfolder_activate(self, *args):
		ret = self.addfolderchooser.run()
		self.addfolderchooser.hide()
		if ret == gtk.RESPONSE_OK:
			
			folders = self.addfolderchooser.get_uris()
			
			filter = None
			if self.combo.get_active():
				filter = os.path.splitext(filepattern[self.combo.get_active()] 
						[1]) [1]

			
			self.filelist.add_uris(folders, filter = filter)

			#base,notused = os.path.split(os.path.commonprefix(folders))
			#filelist = []
			#files = []
			#for folder in folders:
			#  filelist.extend(vfs_walk(gnomevfs.URI(folder)))
			#for f in filelist:
			#  f = f[len(base)+1:]
			#  files.append(SoundFile(base+"/", f))
			#self.filelist.add_files(files)
		self.set_sensitive()

	def on_remove_activate(self, *args):
		model, paths = self.filelist_selection.get_selected_rows()
		while paths:
			i = self.filelist.model.get_iter(paths[0])
			self.filelist.remove(i)
			model, paths = self.filelist_selection.get_selected_rows()
		self.set_sensitive()
		
	def on_clearlist_activate(self, *args):
		self.filelist_selection.select_all();
		model, paths = self.filelist_selection.get_selected_rows()
		while paths:
			i = self.filelist.model.get_iter(paths[0])
			self.filelist.remove(i)
			model, paths = self.filelist_selection.get_selected_rows()
		self.set_sensitive()

	def do_convert(self):
		try:
			for sound_file in self.filelist.get_files():
				self.converter.add(sound_file)
		except ConverterQueueCanceled:
			log(_("canceling conversion."))
			self.conversion_ended()
			self.set_status(_("Conversion canceled"))
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
			self.set_status(_("Waiting for tags"))
			self.progressframe.show()
			self.statusframe.hide()
			self.progress_time = time.time()
			#self.widget.set_sensitive(False)
		
			self.convertion_waiting = True
			self.set_status(_("Waiting for tags..."))
		
			#thread.start_thread(self.do_convert, ())
			self.do_convert()
			#gobject.timeout_add(100, self.wait_tags_and_convert)
		else:
			self.converter.paused = not self.converter.paused
			if self.converter.paused:
				self.set_status(_("Paused"))
			else: 
				self.set_status("") 
		self.set_sensitive()

	def on_button_pause_clicked(self, *args):
		task = self.converter.get_current_task()
		if task:
			self.converter.paused = not self.converter.paused
			task.toggle_pause(self.converter.paused)
		else:
			return
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
		self.progressframe.hide()
		self.statusframe.show()
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
		self.progressbar.set_text(_("Converting file %d of %d  (%s)") % ( self.converter.tasks_done+1, self.converter.tasks_number, remaining ))
	
	def set_progress(self, done_so_far, total, current_file=""):
		if (total==0) or (done_so_far==0):
			self.progressbar.set_text(" ")
			self.progressbar.set_fraction(0.0)
			self.progressbar.pulse()
			return
		if time.time() < self.progress_time + 0.10:
			# ten updates per second should be enough
			return
		self.progress_time = time.time()
		
		self.set_status(_("Converting"))
		
		self.progressfile.set_markup("<i><small>%s</small></i>" % markup_escape(current_file))
		fraction = float(done_so_far) / total
	
		self.progressbar.set_fraction( min(fraction, 1.0) )
		t = time.time() - self.converter.run_start_time - self.converter.paused_time
		
		if (t<1):
			# wait a bit not to display crap
			self.progressbar.pulse()
			return
			
		r = (t / fraction - t)
		#return
		s = r%60
		m = r/60
		remaining = _("%d:%02d left") % (m,s)
		self.display_progress(remaining)

	def set_status(self, text=None):
		if not text:
			text = _("Ready")
		self.status.set_markup(text)


def gui_main(input_files):
	gnome.init(NAME, VERSION)
	glade = gtk.glade.XML(GLADE)
	win = SoundConverterWindow(glade)
	global error
	error = ErrorDialog(glade)
	#TODO
	gobject.idle_add(win.filelist.add_uris, input_files)
	win.set_sensitive()
	#gtk.threads_enter()
	gtk.main()
	#gtk.threads_leave()

def cli_tags_main(input_files):
	global error
	error = ErrorPrinter()
	for input_file in input_files:
		input_file = SoundFile(input_file)
		if not get_option("quiet"):
			print input_file.get_uri()
		t = TagReader(input_file)
		t.setup()
		while t.do_work():
			pass
		t.finish()
		if not get_option("quiet"):
			keys = input_file.keys()
			keys.sort()
			for key in keys:
				print "		%s: %s" % (key, input_file[key])


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

	output_type = get_option("cli-output-type")
	output_suffix = get_option("cli-output-suffix")
	
	generator = TargetNameGenerator()
	generator.set_target_suffix(output_suffix)
	
	progress = CliProgress()
	
	queue = TaskQueue()
	for input_file in input_files:
		input_file = SoundFile(input_file)
		output_name = generator.get_target_name(input_file)
		c = Converter(input_file, output_name, output_type)
		c.overwrite = True
		c.init()
		queue.add(c)

	previous_filename = None
	queue.run()
	while queue.is_running():
		t = queue.get_current_task()
		if t and not get_option("quiet"):
			if previous_filename != t.sound_file.get_filename_for_display():
				if previous_filename:
					print _("%s: OK") % previous_filename
				previous_filename = t.sound_file.get_filename_for_display()

			percent = 0
			if t.get_duration():
				percent = "%.1f %%" % ( 100.0* (t.get_position() / t.get_duration() ))
			else:
				percent = "/-\|" [int(time.time()) % 4]
			progress.show("%s: %s" % (t.sound_file.get_filename_for_display()[-65:], percent ))
		gtk_sleep(0.1)

	if not get_option("quiet"):
		progress.clear()

def cpuCount():
	'''
	Returns the number of CPUs in the system.
	(from pyprocessing)
	'''
	if sys.platform == 'win32':
		try:
			num = int(os.environ['NUMBER_OF_PROCESSORS'])
		except (ValueError, KeyError):
			num = 0
	elif sys.platform == 'darwin':
		try:
			num = int(os.popen('sysctl -n hw.ncpu').read())
		except ValueError:
			num = 0
	else:
		try:
			num = os.sysconf('SC_NPROCESSORS_ONLN')
		except (ValueError, OSError, AttributeError):
			num = 0
	if num >= 1:
		return num
	else:
		return 1
		#raise NotImplementedError, 'cannot determine number of cpus'

settings = {
	"mode": "gui",
	"quiet": False,
	"debug": False,
	"cli-output-type": "audio/x-vorbis",
	"cli-output-suffix": ".ogg",
	"jobs": cpuCount(),
}


def set_option(key, value):
	assert key in settings
	settings[key] = value


def get_option(key):
	assert key in settings
	return settings[key]


def print_help(*args):
	print _("Usage: %s [options] [soundfile ...]") % sys.argv[0]
	for short_arg, long_arg, func, doc in options:
		print
		if short_arg[-1] == ":":
			print "		-%s arg, --%sarg" % (short_arg[:1], long_arg)
		else:
			print "		-%s, --%s" % (short_arg[:1], long_arg)
		for line in textwrap.wrap(doc):
			print "			%s" % line
	sys.exit(0)


options = [

	("h", "help", print_help,
	 _("Print out a usage summary.")),

	("b", "batch", lambda optarg: set_option("mode", "batch"),
	 _("Convert in batch mode, from command line, without a graphical user\n interface. You can use this from, say, shell scripts.")),

	("m:", "mime-type=", lambda optarg: set_option("cli-output-type", optarg),
	 _("Set the output MIME type for batch mode. The default is\n %s . Note that you probably want to set\n the output suffix as well.") % get_option("cli-output-type")),
	 
	("q", "quiet", lambda optarg: set_option("quiet", True),
	 _("Be quiet. Don't write normal output, only errors.")),

	("d", "debug", lambda optarg: set_option("debug", True),
	 _("Print additional debug information")),

	("s:", "suffix=", lambda optarg: set_option("cli-output-suffix", optarg),
	 _("Set the output filename suffix for batch mode. The default is \n %s . Note that the suffix does not affect\n the output MIME type.") % get_option("cli-output-suffix")),

	("t", "tags", lambda optarg: set_option("mode", "tags"),
	 _("Show tags for input files instead of converting them. This indicates \n command line batch mode and disables the graphical user interface.")),

	("j", "jobs=", lambda optarg: set_option("jobs", optarg),
	 _("Force number of concurrent conversions.")),

	]


def main():
	shortopts = "".join(map(lambda opt: opt[0], options))
	longopts = map(lambda opt: opt[1], options)
	
	try:
		opts, args = getopt.getopt(sys.argv[1:], shortopts, longopts)
	except getopt.GetoptError, error:
		print 'Error: ', error
		sys.exit(1)

	for opt, optarg in opts:
		for tuple in options:
			short = "-" + tuple[0][:1]
			long = "--" + tuple[1]
			if long.endswith("="):
				long = long[:-1]
			if opt in [short, long]:
				tuple[2](optarg)
				break

	args = map(filename_to_uri, args)

	jobs = int(get_option('jobs'))
	set_option('jobs', jobs)
	print '  using %d thread(s)' % get_option('jobs')
	
	if get_option("mode") == "gui":
		gui_main(args)
	elif get_option("mode") == "tags":
		cli_tags_main(args)
	else:
		cli_convert_main(args)


if __name__ == "__main__":
	main()
