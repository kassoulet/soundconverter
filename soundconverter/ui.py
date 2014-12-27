#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2014 Gautier Portet
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
from os.path import basename, dirname
from random import random
import time
import sys
import urllib
from gettext import gettext as _

import gtk
import gobject
import gnome
import gnomevfs
from gconfstore import GConfStore
from fileoperations import filename_to_uri, beautify_uri, vfs_writable, \
    vfs_exists
from fileoperations import unquote_filename, vfs_walk
from fileoperations import use_gnomevfs
from gstreamer import ConverterQueue
from gstreamer import available_elements, TypeFinder
from gstreamer import audio_profiles_list, audio_profiles_dict
from soundfile import SoundFile
from settings import locale_patterns_dict, custom_patterns, filepattern, settings
from namegenerator import TargetNameGenerator
from queue import TaskQueue
from utils import log, debug
from messagearea import MessageArea
from error import show_error


# Names of columns in the file list
MODEL = [ gobject.TYPE_STRING,   # visible filename
          gobject.TYPE_PYOBJECT, # soundfile
          gobject.TYPE_FLOAT,    # progress
          gobject.TYPE_STRING,   # status
          gobject.TYPE_STRING,   # complete filename
    ]

COLUMNS = ['filename']

#VISIBLE_COLUMNS = ['filename']
#ALL_COLUMNS = VISIBLE_COLUMNS + ['META']

MP3_CBR, MP3_ABR, MP3_VBR = range(3)


def gtk_iteration():
    while gtk.events_pending():
        gtk.main_iteration(False)


def gtk_sleep(duration):
    start = time.time()
    while time.time() < start + duration:
        time.sleep(0.010)
        gtk_iteration()


class ErrorDialog:

    def __init__(self, builder):
        self.dialog = builder.get_object('error_dialog')
        self.dialog.set_transient_for(builder.get_object('window'))
        self.primary = builder.get_object('primary_error_label')
        self.secondary = builder.get_object('secondary_error_label')

    def show_error(self, primary, secondary):
        self.primary.set_markup(primary)
        self.secondary.set_markup(secondary)
        try:
            sys.stderr.write(_('\nError: %s\n%s\n') % (primary, secondary))
        except:
            pass
        self.dialog.run()
        self.dialog.hide()


class MsgAreaErrorDialog_:

    def __init__(self, builder):
        self.dialog = builder.get_object('error_frame')
        self.primary = builder.get_object('label_error')

    def show_error(self, primary, secondary):
        try:
            sys.stderr.write(_('\nError: %s\n%s\n') % (primary, secondary))
        except:
            pass
        #self.msg_area.set_text_and_icon(gtk.STOCK_DIALOG_ERROR, primary, secondary)
        #self.msg_area.show()
        self.primary.set_text(primary)
        self.dialog.show()


    def show_exception(self, exception):
        self.show('<b>%s</b>' % gobject.markup_escape_text(exception.primary),
                    exception.secondary)


class FileList:
    """List of files added by the user."""

    # List of MIME types which we accept for drops.
    drop_mime_types = ['text/uri-list', 'text/plain', 'STRING']

    def __init__(self, window, builder):
        self.window = window
        self.typefinders = TaskQueue()
        self.filelist = set()

        self.model = apply(gtk.ListStore, MODEL)

        self.widget = builder.get_object('filelist')
        self.sortedmodel = gtk.TreeModelSort(self.model)
        self.widget.set_model(self.sortedmodel)
        self.sortedmodel.set_sort_column_id(4, gtk.SORT_ASCENDING)
        self.widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        self.widget.drag_dest_set(gtk.DEST_DEFAULT_ALL,
                                    map(lambda i:
                                        (self.drop_mime_types[i], 0, i),
                                        range(len(self.drop_mime_types))),
                                        gtk.gdk.ACTION_COPY)
        self.widget.connect('drag_data_received', self.drag_data_received)

        renderer = gtk.CellRendererProgress()
        column = gtk.TreeViewColumn('progress',
                                    renderer,
                                    value=2,
                                    text=3,
                                    )
        self.widget.append_column(column)
        self.progress_column = column
        self.progress_column.set_visible(False)

        renderer = gtk.CellRendererText()
        import pango
        renderer.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        column = gtk.TreeViewColumn('Filename',
                                    renderer,
                                    markup=0,
                                    )
        column.set_expand(True)
        self.widget.append_column(column)

        self.window.progressbarstatus.hide()
        
        self.waiting_files = []
        # add files to filelist in batches. Much faster, and suffisant.
        gobject.timeout_add(100, self.commit_waiting_files)
        self.waiting_files_last = 0

    def drag_data_received(self, widget, context, x, y, selection,
                             mime_id, time):
        widget.stop_emission('drag_data_received')
        if mime_id >= 0 and mime_id < len(self.drop_mime_types):
            uris = [filename_to_uri(uri.strip()) for uri in selection.data.split('\n')]
            self.add_uris(uris)
            context.finish(True, False, time)

    def get_files(self):
        return [i[1] for i in self.sortedmodel]

    def update_progress(self, queue):
        if queue.running:
            progress = queue.progress if queue.progress else 0
            self.window.progressbarstatus.set_fraction(progress)
            return True
        return False

    def found_type(self, sound_file, mime):
        debug('found_type', sound_file.filename)

        self.append_file(sound_file)
        self.window.set_sensitive()

    def add_uris(self, uris, base=None, extensions=None):
        files = []
        self.window.set_status(_('Scanning files...'))

        base = None

        for uri in uris:
            if not uri:
                continue
            if uri.startswith('cdda:'):
                show_error('Cannot read from Audio CD.',
                    'Use SoundJuicer Audio CD Extractor instead.')
                return
            try:
                info = gnomevfs.get_file_info(gnomevfs.URI(uri),
                            gnomevfs.FILE_INFO_FOLLOW_LINKS)
            except gnomevfs.NotFoundError:
                log('uri not found: \'%s\'' % uri)
                continue
            except gnomevfs.InvalidURIError:
                log('invalid uri: \'%s\'' % uri)
                continue
            except gnomevfs.AccessDeniedError:
                log('access denied: \'%s\'' % uri)
                continue
            except TypeError, e:
                log('add error: %s (\'%s\')' % (e, uri))
                continue
            except:
                log('error in get_file_info: %s' % (uri))
                continue

            if info.type == gnomevfs.FILE_TYPE_DIRECTORY:
                log('walking: \'%s\'' % uri)
                if len(uris) == 1:
                    # if only one folder is passed to the function,
                    # use its parent as base path.
                    base = os.path.dirname(uri)
                filelist = vfs_walk(gnomevfs.URI(uri))
                accepted = []
                if extensions:
                    for f in filelist:
                        for extension in extensions:
                            if f.lower().endswith(extension):
                                accepted.append(f)
                    filelist = accepted
                files.extend(filelist)
            else:
                files.append(uri)

        files = [f for f in files if not f.endswith('~SC~')]

        if not base:
            base = os.path.commonprefix(files)
            if base and not base.endswith('/'):
                # we want a common folder
                base = base[0:base.rfind('/')]
                base += '/'
        else:
            base += '/'

        for f in files:
            sound_file = SoundFile(f, base)
            if sound_file.uri in self.filelist:
                log('file already present: \'%s\'' % sound_file.uri)
                continue

            typefinder = TypeFinder(sound_file)
            typefinder.set_found_type_hook(self.found_type)
            self.typefinders.add_task(typefinder)

        for i in self.model:
            i[0] = self.format_cell(i[1])

        if files and not self.typefinders.running:
            self.window.progressbarstatus.show()
            self.typefinders.queue_ended = self.typefinder_queue_ended
            self.typefinders.start()
            gobject.timeout_add(100, self.update_progress, self.typefinders)
        else:
            self.window.set_status()

    def typefinder_queue_ended(self):
        if not self.waiting_files:
            self.window.set_status()
            self.window.progressbarstatus.hide()

    def abort(self):
        self.typefinders.abort()

    def format_cell(self, sound_file):
        return '%s' % gobject.markup_escape_text(unquote_filename(
                                                  sound_file.filename))

    def set_row_progress(self, number, progress=None, text=None):
        self.progress_column.set_visible(True)
        if progress is not None:
            if self.model[number][2] == 1.0:
                return # already...
            self.model[number][2] = progress * 100.0
        if text is not None:
            self.model[number][3] = text

    def hide_row_progress(self):
        self.progress_column.set_visible(False)

    def append_file(self, sound_file):
        self.waiting_files.append(sound_file)

    def commit_waiting_files(self):
        if self.waiting_files_last != len(self.waiting_files):
            # still adding files
            self.waiting_files_last = len(self.waiting_files)
            return True
        
        if self.waiting_files:
            self.window.set_status(_('Adding files...'))
            save = self.widget.get_model()
            self.widget.set_model(None)
            n = 0.0
            next = time.time()
            while self.waiting_files:
                self._append_file(self.waiting_files.pop())
                n += 1
                if time.time() > next: 
                    # keep UI responsive
                    gtk_iteration() 
                    self.window.progressbarstatus.set_fraction(n/self.waiting_files_last)
                    next = time.time() + 0.01
            self.widget.set_model(save)
            
            self.window.set_status()
            self.window.progressbarstatus.hide()
        return True

    def _append_file(self, sound_file):
        self.model.append([self.format_cell(sound_file), sound_file, 0.0, '',
                           sound_file.uri])
        self.filelist.add(sound_file.uri)
        sound_file.filelist_row = len(self.model) - 1

    def remove(self, iter):
        uri = self.model.get(iter, 1)[0].uri
        self.filelist.remove(uri)
        self.model.remove(iter)

    def is_nonempty(self):
        try:
            self.model.get_iter((0,))
        except ValueError:
            return False
        return True


class GladeWindow(object):

    callbacks = {}
    builder = None

    def __init__(self, builder):
        '''
        Init GladeWindow, stores the objects's potential callbacks for later.
        You have to call connect_signals() when all descendants are ready.'''
        GladeWindow.builder = builder
        GladeWindow.callbacks.update(dict([[x, getattr(self, x)]
                                     for x in dir(self) if x.startswith('on_')]))

    def __getattr__(self, attribute):
        '''Allow direct use of window widget.'''
        widget = GladeWindow.builder.get_object(attribute)
        if widget is None:
            raise AttributeError('Widget \'%s\' not found' % attribute)
        self.__dict__[attribute] = widget # cache result
        return widget

    @staticmethod
    def connect_signals():
        '''Connect all GladeWindow objects to theirs respective signals'''
        GladeWindow.builder.connect_signals(GladeWindow.callbacks)


class PreferencesDialog(GladeWindow, GConfStore):

    basename_patterns = [
        ('%(.inputname)s', _('Same as input, but replacing the suffix')),
        ('%(.inputname)s%(.ext)s',
                            _('Same as input, but with an additional suffix')),
        ('%(track-number)02d-%(title)s', _('Track number - title')),
        ('%(title)s', _('Track title')),
        ('%(artist)s-%(title)s', _('Artist - title')),
        ('Custom', _('Custom filename pattern')),
    ]

    subfolder_patterns = [
        ('%(artist)s/%(album)s', _('artist/album')),
        ('%(artist)s-%(album)s', _('artist-album')),
        ('%(artist)s - %(album)s', _('artist - album')),
    ]

    defaults = {
        'same-folder-as-input': 1,
        'selected-folder': os.path.expanduser('~'),
        'create-subfolders': 0,
        'subfolder-pattern-index': 0,
        'name-pattern-index': 0,
        'custom-filename-pattern': '{Track} - {Title}',
        'replace-messy-chars': 0,
        'output-mime-type': 'audio/x-vorbis',
        'output-suffix': '.ogg',
        'vorbis-quality': 0.6,
        'vorbis-oga-extension': 0,
        'mp3-mode': 'vbr',
        'mp3-cbr-quality': 192,
        'mp3-abr-quality': 192,
        'mp3-vbr-quality': 3,
        'aac-quality': 192,
        'opus-bitrate': 96,
        'flac-compression': 8,
        'wav-sample-width': 16,
        'delete-original': 0,
        'output-resample': 0,
        'resample-rate': 48000,
        'flac-speed': 0, # TODO used ?
        'force-mono': 0,
        'last-used-folder': None,
        'audio-profile': None,
        'limit-jobs': 0,
        'number-of-jobs': 1,
    }

    sensitive_names = ['vorbis_quality', 'choose_folder', 'create_subfolders',
                       'subfolder_pattern', 'jobs_spinbutton', 'resample_hbox',
                       'force_mono']

    def __init__(self, builder, parent):
        GladeWindow.__init__(self, builder)
        GConfStore.__init__(self, '/apps/SoundConverter', self.defaults)

        self.dialog = builder.get_object('prefsdialog')
        self.dialog.set_transient_for(parent)
        self.example = builder.get_object('example_filename')
        self.force_mono = builder.get_object('force_mono')

        self.target_bitrate = None
        self.convert_setting_from_old_version()

        self.sensitive_widgets = {}
        for name in self.sensitive_names:
            self.sensitive_widgets[name] = builder.get_object(name)
            assert self.sensitive_widgets[name] is not None
        self.set_widget_initial_values(builder)
        self.set_sensitive()

        tip = [_('Available patterns:')]
        for k in sorted(locale_patterns_dict.values()):
            tip.append(k)
        self.custom_filename.set_tooltip_text('\n'.join(tip))

        #self.resample_rate.connect('changed', self._on_resample_rate_changed)

    def convert_setting_from_old_version(self):
        """ try to convert previous settings"""

        # vorbis quality was once stored as an int enum
        try:
            self.get_float('vorbis-quality')
        except gobject.GError:
            log('deleting old settings...')
            [self.gconf.unset(self.path(k)) for k in self.defaults.keys()]

        self.gconf.clear_cache()

    def set_widget_initial_values(self, builder):

        self.quality_tabs.set_show_tabs(False)

        if self.get_int('same-folder-as-input'):
            w = self.same_folder_as_input
        else:
            w = self.into_selected_folder
        w.set_active(True)

        uri = filename_to_uri(self.get_string('selected-folder'))
        self.target_folder_chooser.set_uri(uri)
        self.target_folder_chooser.set_local_only(not use_gnomevfs)
        self.update_selected_folder()

        w = self.create_subfolders
        w.set_active(self.get_int('create-subfolders'))

        w = self.subfolder_pattern
        active = self.get_int('subfolder-pattern-index')
        model = w.get_model()
        model.clear()
        for pattern, desc in self.subfolder_patterns:
            i = model.append()
            model.set(i, 0, desc)
        w.set_active(active)

        if self.get_int('replace-messy-chars'):
            w = self.replace_messy_chars
            w.set_active(True)

        if self.get_int('delete-original'):
            self.delete_original.set_active(True)

        mime_type = self.get_string('output-mime-type')

        widgets = ( ('audio/x-vorbis', 'vorbisenc'),
                    ('audio/mpeg'    , 'lame'),
                    ('audio/x-flac'  , 'flacenc'),
                    ('audio/x-wav'   , 'wavenc'),
                    ('audio/x-m4a'   , 'faac'),
                    ('audio/ogg; codecs=opus'   , 'opusenc'),
                    ('gst-profile'   , None),
                    ) # must be in same order in output_mime_type

        # desactivate output if encoder plugin is not present
        widget = self.output_mime_type
        model = widget.get_model()
        assert len(model) == len(widgets), 'model:%d widgets:%d' % (len(model),
                                                                 len(widgets))

        if not self.gstprofile.get_model().get_n_columns():
            self.gstprofile.set_model(gtk.ListStore(str))
            cell = gtk.CellRendererText()
            self.gstprofile.pack_start(cell)
            self.gstprofile.add_attribute(cell,'text',0)
            self.gstprofile.set_active(0)

        # check if we can found the stored audio profile
        found_profile = False
        stored_profile = self.get_string('audio-profile')
        for i, profile in enumerate(audio_profiles_list):
            description, extension, pipeline = profile
            self.gstprofile.get_model().append(['%s (.%s)' % (description, extension)])
            if description == stored_profile:
                self.gstprofile.set_active(i)
                found_profile = True
        if not found_profile and stored_profile:
            # reset default output
            log('Cannot find audio profile "%s", resetting to default output.'
                % stored_profile)
            self.set_string('audio-profile', '')
            self.gstprofile.set_active(0)
            mime_type = self.defaults['output-mime-type']

        self.present_mime_types = []
        i = 0
        model = self.output_mime_type.get_model()
        for b in widgets:
            mime, encoder_name = b
            # valid encoder?
            encoder_present = encoder_name and encoder_name in available_elements
            # valid profile?
            profile_present = mime == 'gst-profile' and audio_profiles_list
            if encoder_present or profile_present:
                # add to supported outputs
                self.present_mime_types.append(mime)
                i += 1
            else:
                # remove it.
                del model[i]
                if mime_type == mime:
                    mime_type = self.defaults['output-mime-type']
        for i, mime in enumerate(self.present_mime_types):
            if mime_type == mime:
                widget.set_active(i)
        self.change_mime_type(mime_type)

        # display information about mp3 encoding
        if 'lame' not in available_elements:
            w = self.lame_absent
            w.show()

        w = self.vorbis_quality
        quality = self.get_float('vorbis-quality')
        quality_setting = {0: 0, 0.2: 1, 0.4: 2, 0.6: 3, 0.8: 4, 1.0: 5}
        w.set_active(-1)
        for k, v in quality_setting.iteritems():
            if abs(quality - k) < 0.01:
                self.vorbis_quality.set_active(v)
        if self.get_int('vorbis-oga-extension'):
            self.vorbis_oga_extension.set_active(True)

        w = self.aac_quality
        quality = self.get_int('aac-quality')
        quality_setting = {64: 0, 96: 1, 128: 2, 192: 3, 256: 4, 320: 5}
        w.set_active(quality_setting.get(quality, -1))

        w = self.opus_quality
        quality = self.get_int('opus-bitrate')
        quality_setting = {48: 0, 64: 1, 96: 2, 128: 3, 160: 4, 192: 5}
        w.set_active(quality_setting.get(quality, -1))

        w = self.flac_compression
        quality = self.get_int('flac-compression')
        quality_setting = {0: 0, 5: 1, 8: 2}
        w.set_active(quality_setting.get(quality, -1))

        w = self.wav_sample_width
        quality = self.get_int('wav-sample-width')
        quality_setting = {8: 0, 16: 1, 32: 2}
        w.set_active(quality_setting.get(quality, -1))

        self.mp3_quality = self.mp3_quality
        self.mp3_mode = self.mp3_mode

        mode = self.get_string('mp3-mode')
        self.change_mp3_mode(mode)

        w = self.basename_pattern
        active = self.get_int('name-pattern-index')
        model = w.get_model()
        model.clear()
        for pattern, desc in self.basename_patterns:
            iter = model.append()
            model.set(iter, 0, desc)
        w.set_active(active)

        self.custom_filename.set_text(self.get_string(
                                                    'custom-filename-pattern'))
        if self.basename_pattern.get_active() == len(self.basename_patterns)-1:
            self.custom_filename_box.set_sensitive(True)
        else:
            self.custom_filename_box.set_sensitive(False)


        self.resample_toggle.set_active(self.get_int('output-resample'))

        cell = gtk.CellRendererText()
        self.resample_rate.pack_start(cell, True)
        self.resample_rate.add_attribute(cell, 'text', 0)
        rates = [8000, 11025, 22050, 44100, 48000, 96000]
        rate = self.get_int('resample-rate')
        try:
            idx = rates.index(rate)
        except ValueError:
            idx = -1
        self.resample_rate.set_active(idx)

        self.force_mono.set_active(self.get_int('force-mono'))

        self.jobs.set_active(self.get_int('limit-jobs'))
        self.jobs_spinbutton.set_value(self.get_int('number-of-jobs'))

        self.update_jobs()
        self.update_example()

    def update_selected_folder(self):
        self.into_selected_folder.set_use_underline(False)
        self.into_selected_folder.set_label(_('Into folder %s') %
            beautify_uri(self.get_string('selected-folder')))

    def get_bitrate_from_settings(self):
        bitrate = 0
        aprox = True
        mode = self.get_string('mp3-mode')

        mime_type = self.get_string('output-mime-type')

        if mime_type == 'audio/x-vorbis':
            quality = self.get_float('vorbis-quality')*10
            quality = int(quality)
            bitrates = (64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 500)
            bitrate = bitrates[quality]

        elif mime_type == 'audio/x-m4a':
            bitrate = self.get_int('aac-quality')

        elif mime_type == 'audio/ogg; codecs=opus':
            bitrate = self.get_int('opus-bitrate')

        elif mime_type == 'audio/mpeg':
            quality = {
                'cbr': 'mp3-cbr-quality',
                'abr': 'mp3-abr-quality',
                'vbr': 'mp3-vbr-quality'
            }
            bitrate = self.get_int(quality[mode])
            if mode == 'vbr':
                # hum, not really, but who cares? :)
                bitrates = (320, 256, 224, 192, 160, 128, 112, 96, 80, 64)
                bitrate = bitrates[bitrate]
            if mode == 'cbr':
                aprox = False

        if bitrate:
            if aprox:
                return '~%d kbps' % bitrate
            else:
                return '%d kbps' % bitrate
        else:
            return 'N/A'

    def update_example(self):
        sound_file = SoundFile('foo/bar.flac')
        sound_file.tags.update({'track-number': 1, 'track-count': 99})
        sound_file.tags.update({'disc-number': 2, 'disc-count': 9})
        sound_file.tags.update(locale_patterns_dict)

        s = gobject.markup_escape_text(beautify_uri(
                        self.generate_filename(sound_file, for_display=True)))
        p = 0
        replaces = []

        while 1:
            b = s.find('{', p)
            if b == -1:
                break
            e = s.find('}', b)

            tag = s[b:e+1]
            if tag.lower() in [
                            v.lower() for v in locale_patterns_dict.values()]:
                k = tag
                l = k.replace('{', '<b>{')
                l = l.replace('}', '}</b>')
                replaces.append([k, l])
            else:
                k = tag
                l = k.replace('{', '<span foreground=\'red\'><i>{')
                l = l.replace('}', '}</i></span>')
                replaces.append([k, l])
            p = b+1

        for k, l in replaces:
            s = s.replace(k, l)

        self.example.set_markup(s)

        markup = '<small>%s</small>' % (_('Target bitrate: %s') %
                    self.get_bitrate_from_settings())
        self.aprox_bitrate.set_markup(markup)

    def get_output_suffix(self):
        self.gconf.clear_cache()
        output_type = self.get_string('output-mime-type')
        profile = self.get_string('audio-profile')
        profile_ext = audio_profiles_dict[profile][1] if profile else ''
        output_suffix = {
                'audio/x-vorbis': '.ogg',
                'audio/x-flac': '.flac',
                'audio/x-wav': '.wav',
                'audio/mpeg': '.mp3',
                'audio/x-m4a': '.m4a',
                'audio/ogg; codecs=opus': '.opus',
                'gst-profile': '.' + profile_ext,
        }.get(output_type, '.?')
        if output_suffix == '.ogg' and self.get_int('vorbis-oga-extension'):
            output_suffix = '.oga'
        return output_suffix

    def generate_filename(self, sound_file, for_display=False):
        generator = TargetNameGenerator()
        generator.suffix = self.get_output_suffix()

        if not self.get_int('same-folder-as-input'):
            folder = self.get_string('selected-folder')
            folder = filename_to_uri(folder)
            generator.folder = folder

            if self.get_int('create-subfolders'):
                generator.subfolders = self.get_subfolder_pattern()

        generator.basename = self.get_basename_pattern()

        if for_display:
            generator.replace_messy_chars = False
            return unquote_filename(generator.get_target_name(sound_file))
        else:
            generator.replace_messy_chars = self.get_int('replace-messy-chars')
            return generator.get_target_name(sound_file)

    def generate_temp_filename(self, soundfile):
        folder = dirname(soundfile.uri)
        if not self.get_int('same-folder-as-input'):
            folder = self.get_string('selected-folder')
            folder = filename_to_uri(folder)

        while True:
            filename = folder + '/' + basename(soundfile.filename) + '~' + str(random())[-6:] + '~SC~'
            if not vfs_exists(filename):
                return filename

    def process_custom_pattern(self, pattern):
        for k in custom_patterns:
            pattern = pattern.replace(k, custom_patterns[k])
        return pattern

    def set_sensitive(self):
        for widget in self.sensitive_widgets.values():
            widget.set_sensitive(False)

        x = self.get_int('same-folder-as-input')
        for name in ['choose_folder', 'create_subfolders',
                     'subfolder_pattern']:
            self.sensitive_widgets[name].set_sensitive(not x)

        self.sensitive_widgets['vorbis_quality'].set_sensitive(
            self.get_string('output-mime-type') == 'audio/x-vorbis')

        self.sensitive_widgets['jobs_spinbutton'].set_sensitive(
            self.get_int('limit-jobs'))

        if self.get_string('output-mime-type') == 'gst-profile':
            self.sensitive_widgets['resample_hbox'].set_sensitive(False)
            self.sensitive_widgets['force_mono'].set_sensitive(False)
        else:
            self.sensitive_widgets['resample_hbox'].set_sensitive(True)
            self.sensitive_widgets['force_mono'].set_sensitive(True)


    def run(self):
        self.dialog.run()
        self.dialog.hide()

    def on_delete_original_toggled(self, button):
        if button.get_active():
            self.set_int('delete-original', 1)
        else:
            self.set_int('delete-original', 0)

    def on_same_folder_as_input_toggled(self, button):
        if button.get_active():
            self.set_int('same-folder-as-input', 1)
            self.set_sensitive()
            self.update_example()

    def on_into_selected_folder_toggled(self, button):
        if button.get_active():
            self.set_int('same-folder-as-input', 0)
            self.set_sensitive()
            self.update_example()

    def on_choose_folder_clicked(self, button):
        ret = self.target_folder_chooser.run()
        folder = self.target_folder_chooser.get_uri()
        self.target_folder_chooser.hide()
        if ret == gtk.RESPONSE_OK:
            writable = vfs_writable(folder)
            if not writable:
                show_error(_('Cannot write to folder'), _('"%s" folder is not writable.') % folder)
                return
            if folder:
                self.set_string('selected-folder', urllib.unquote(folder))
                self.update_selected_folder()
                self.update_example()

    def on_create_subfolders_toggled(self, button):
        if button.get_active():
            self.set_int('create-subfolders', 1)
        else:
            self.set_int('create-subfolders', 0)
        self.update_example()

    def on_subfolder_pattern_changed(self, combobox):
        self.set_int('subfolder-pattern-index', combobox.get_active())
        self.update_example()

    def get_subfolder_pattern(self):
        index = self.get_int('subfolder-pattern-index')
        if index < 0 or index >= len(self.subfolder_patterns):
            index = 0
        return self.subfolder_patterns[index][0]

    def on_basename_pattern_changed(self, combobox):
        self.set_int('name-pattern-index', combobox.get_active())
        if combobox.get_active() == len(self.basename_patterns)-1:
            self.custom_filename_box.set_sensitive(True)
        else:
            self.custom_filename_box.set_sensitive(False)
        self.update_example()

    def get_basename_pattern(self):
        index = self.get_int('name-pattern-index')
        if index < 0 or index >= len(self.basename_patterns):
            index = 0
        if self.basename_pattern.get_active() == len(self.basename_patterns)-1:
            return self.process_custom_pattern(self.custom_filename.get_text())
        else:
            return self.basename_patterns[index][0]

    def on_custom_filename_changed(self, entry):
        self.set_string('custom-filename-pattern', entry.get_text())
        self.update_example()

    def on_replace_messy_chars_toggled(self, button):
        if button.get_active():
            self.set_int('replace-messy-chars', 1)
        else:
            self.set_int('replace-messy-chars', 0)
        self.update_example()

    def change_mime_type(self, mime_type):
        self.set_string('output-mime-type', mime_type)
        self.set_sensitive()
        self.update_example()
        tabs = {
                        'audio/x-vorbis': 0,
                        'audio/mpeg': 1,
                        'audio/x-flac': 2,
                        'audio/x-wav': 3,
                        'audio/x-m4a': 4,
                        'audio/ogg; codecs=opus': 5,
                        'gst-profile': 6,
        }
        self.quality_tabs.set_current_page(tabs[mime_type])

    def on_output_mime_type_changed(self, combo):
        self.change_mime_type(
            self.present_mime_types[combo.get_active()]
        )

    def on_output_mime_type_ogg_vorbis_toggled(self, button):
        if button.get_active():
            self.change_mime_type('audio/x-vorbis')

    def on_output_mime_type_flac_toggled(self, button):
        if button.get_active():
            self.change_mime_type('audio/x-flac')

    def on_output_mime_type_wav_toggled(self, button):
        if button.get_active():
            self.change_mime_type('audio/x-wav')

    def on_output_mime_type_mp3_toggled(self, button):
        if button.get_active():
            self.change_mime_type('audio/mpeg')

    def on_output_mime_type_aac_toggled(self, button):
        if button.get_active():
            self.change_mime_type('audio/x-m4a')

    def on_output_mime_type_opus_toggled(self, button):
        if button.get_active():
            self.change_mime_type('audio/ogg; codecs=opus')

    def on_vorbis_quality_changed(self, combobox):
        if combobox.get_active() == -1:
            return # just de-selectionning
        quality = (0, 0.2, 0.4, 0.6, 0.8, 1.0)
        fquality = quality[combobox.get_active()]
        self.set_float('vorbis-quality', fquality)
        self.hscale_vorbis_quality.set_value(fquality*10)
        self.update_example()

    def on_hscale_vorbis_quality_value_changed(self, hscale):
        fquality = hscale.get_value()
        if abs(self.get_float('vorbis-quality') - fquality/10.0) < 0.001:
            return # already at right value
        self.set_float('vorbis-quality', fquality/10.0)
        self.vorbis_quality.set_active(-1)
        self.update_example()

    def on_vorbis_oga_extension_toggled(self, toggle):
        self.set_int('vorbis-oga-extension', toggle.get_active())
        self.update_example()

    def on_aac_quality_changed(self, combobox):
        quality = (64, 96, 128, 192, 256, 320)
        self.set_int('aac-quality', quality[combobox.get_active()])
        self.update_example()

    def on_opus_quality_changed(self, combobox):
        quality = (48, 64, 96, 128, 160, 192)
        self.set_int('opus-bitrate', quality[combobox.get_active()])
        self.update_example()

    def on_wav_sample_width_changed(self, combobox):
        quality = (8, 16, 32)
        self.set_int('wav-sample-width', quality[combobox.get_active()])
        self.update_example()

    def on_flac_compression_changed(self, combobox):
        quality = (0, 5, 8)
        self.set_int('flac-compression', quality[combobox.get_active()])
        self.update_example()

    def on_gstprofile_changed(self, combobox):
        profile = audio_profiles_list[combobox.get_active()]
        description, extension, pipeline = profile
        self.set_string('audio-profile', description)
        self.update_example()

    def on_force_mono_toggle(self, button):
        if button.get_active():
            self.set_int('force-mono', 1)
        else:
            self.set_int('force-mono', 0)
        self.update_example()

    def change_mp3_mode(self, mode):

        keys = {'cbr': 0, 'abr': 1, 'vbr': 2}
        self.mp3_mode.set_active(keys[mode])

        keys = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality',
        }
        quality = self.get_int(keys[mode])

        quality_to_preset = {
            'cbr': {64: 0, 96: 1, 128: 2, 192: 3, 256: 4, 320: 5},
            'abr': {64: 0, 96: 1, 128: 2, 192: 3, 256: 4, 320: 5},
            'vbr': {9: 0, 7: 1, 5: 2, 3: 3, 1: 4, 0: 5}, # inverted !
        }

        range_ = {
            'cbr': 14,
            'abr': 14,
            'vbr': 10,
        }
        self.hscale_mp3.set_range(0, range_[mode])

        if quality in quality_to_preset[mode]:
            self.mp3_quality.set_active(quality_to_preset[mode][quality])
        self.update_example()

    def on_mp3_mode_changed(self, combobox):
        mode = ('cbr', 'abr', 'vbr')[combobox.get_active()]
        self.set_string('mp3-mode', mode)
        self.change_mp3_mode(mode)

    def on_mp3_quality_changed(self, combobox):
        keys = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }
        quality = {
            'cbr': (64, 96, 128, 192, 256, 320),
            'abr': (64, 96, 128, 192, 256, 320),
            'vbr': (9, 7, 5, 3, 1, 0),
        }
        mode = self.get_string('mp3-mode')
        self.set_int(keys[mode], quality[mode][combobox.get_active()])
        self.update_example()

    def on_hscale_mp3_value_changed(self, widget):
        mode = self.get_string('mp3-mode')
        keys = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }
        quality = {
            'cbr': (32, 40, 48, 56, 64, 80, 96, 112,
                    128, 160, 192, 224, 256, 320),
            'abr': (32, 40, 48, 56, 64, 80, 96, 112,
                    128, 160, 192, 224, 256, 320),
            'vbr': (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
        }
        self.set_int(keys[mode], quality[mode][int(widget.get_value())])
        self.mp3_quality.set_active(-1)
        self.update_example()

    def on_resample_rate_changed(self, combobox):
        model = combobox.get_model()
        iter = combobox.get_active_iter()
        changeto =  model.get_value(iter, 0)
        self.set_int('resample-rate', int(changeto))

    def on_resample_toggle(self, rstoggle):
        self.set_int('output-resample', rstoggle.get_active())
        self.resample_rate.set_sensitive(rstoggle.get_active())

    def on_jobs_toggled(self, jtoggle):
        self.set_int('limit-jobs', jtoggle.get_active())
        self.jobs_spinbutton.set_sensitive(jtoggle.get_active())
        self.update_jobs()

    def on_jobs_spinbutton_value_changed(self, jspinbutton):
        self.set_int('number-of-jobs', int(jspinbutton.get_value()))
        self.update_jobs()

    def update_jobs(self):
        if self.get_int('limit-jobs'):
            settings['jobs'] = self.get_int('number-of-jobs')
        else:
            settings['jobs'] = settings['max-jobs']
        self.set_sensitive()


class CustomFileChooser:
    """
    Custom file chooser.\n
    """

    def __init__(self, builder, parent):
        """
        Constructor
        Load glade object, create a combobox
        """
        self.dlg = builder.get_object('custom_file_chooser')
        self.dlg.set_title(_('Open a file'))
        self.dlg.set_transient_for(parent)

        # setup
        self.fcw = builder.get_object('filechooserwidget')
        self.fcw.set_local_only(not use_gnomevfs)
        self.fcw.set_select_multiple(True)

        self.pattern = []

        # Create combobox model
        self.combo = builder.get_object('filtercombo')
        self.combo.connect('changed', self.on_combo_changed)
        self.store = gtk.ListStore(str)
        self.combo.set_model(self.store)
        combo_rend = gtk.CellRendererText()
        self.combo.pack_start(combo_rend, True)
        self.combo.add_attribute(combo_rend, 'text', 0)

        # TODO: get all (gstreamer) knew files
        for name, pattern in filepattern:
            self.add_pattern(name, pattern)
        self.combo.set_active(0)

    def add_pattern(self, name, pat):
        """
        Add a new pattern to the combobox.
        @param name: The pattern name.
        @type name: string
        @param pat: the pattern
        @type pat: string
        """
        self.pattern.append(pat)
        self.store.append(['%s (%s)' % (name, pat)])

    def filter_cb(self, info, pattern):
        filename = info[2]
        return filename.lower().endswith(pattern[1:])

    def on_combo_changed(self, w):
        """
        Callback for combobox 'changed' signal\n
        Set a new filter for the filechooserwidget
        """
        filter = gtk.FileFilter()
        active = self.combo.get_active()
        if active:
            filter.add_custom(gtk.FILE_FILTER_DISPLAY_NAME, self.filter_cb,
                                        self.pattern[self.combo.get_active()])
        else:
            filter.add_pattern('*.*')
        self.fcw.set_filter(filter)

    def __getattr__(self, attr):
        """
        Redirect all missing attributes/methods
        to dialog.
        """
        try:
            # defaut to dialog attributes
            return getattr(self.dlg, attr)
        except AttributeError:
            # fail back to inner file chooser widget
            return getattr(self.fcw, attr)

_old_progress = 0
_old_total = 0

class SoundConverterWindow(GladeWindow):

    """Main application class."""

    sensitive_names = ['remove', 'clearlist',
                       'toolbutton_clearlist', 'convert_button']
    unsensitive_when_converting = ['remove', 'clearlist', 'prefs_button',
            'toolbutton_addfile', 'toolbutton_addfolder', 'convert_button',
            'toolbutton_clearlist', 'filelist', 'menubar']

    def __init__(self, builder):
        self.paused_time = 0
        GladeWindow.__init__(self, builder)

        self.widget = builder.get_object('window')
        self.prefs = PreferencesDialog(builder, self.widget)
        self.addchooser = CustomFileChooser(builder, self.widget)
        GladeWindow.connect_signals()

        self.filelist = FileList(self, builder)
        self.filelist_selection = self.filelist.widget.get_selection()
        self.filelist_selection.connect('changed', self.selection_changed)
        self.existsdialog = builder.get_object('existsdialog')
        self.existsdialog.message = builder.get_object('exists_message')
        self.existsdialog.apply_to_all = builder.get_object('apply_to_all')

        self.addfolderchooser = gtk.FileChooserDialog(_('Add Folder...'),
            self.widget, gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN,
            gtk.RESPONSE_OK))
        self.addfolderchooser.set_select_multiple(True)
        self.addfolderchooser.set_local_only(not use_gnomevfs)

        self.combo = gtk.ComboBox()
        self.store = gtk.ListStore(str)
        self.combo.set_model(self.store)
        combo_rend = gtk.CellRendererText()
        self.combo.pack_start(combo_rend, True)
        self.combo.add_attribute(combo_rend, 'text', 0)

        # TODO: get all (gstreamer) knew files
        for files in filepattern:
            self.store.append(['%s (%s)' % (files[0], files[1])])

        self.combo.set_active(0)
        self.addfolderchooser.set_extra_widget(self.combo)

        self.aboutdialog.set_property('name', NAME)
        self.aboutdialog.set_property('version', VERSION)
        self.aboutdialog.set_transient_for(self.widget)

        self.converter = ConverterQueue(self)

        self.sensitive_widgets = {}
        for name in self.sensitive_names:
            self.sensitive_widgets[name] = builder.get_object(name)
        for name in self.unsensitive_when_converting:
            self.sensitive_widgets[name] = builder.get_object(name)

        self.set_sensitive()
        self.set_status()


        #msg = _('The output file <i>%s</i>\n exists already.\n '\
        #            'Do you want to skip the file, overwrite it or'\
        #            ' cancel the conversion?\n') % '/foo/bar/baz'
        vbox = self.vbox_status
        self.msg_area = msg_area = MessageArea()
        #msg_area.add_button('_Overwrite', 1)
        #msg_area.add_button('_Skip', 2)
        msg_area.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)
        #checkbox = gtk.CheckButton('Apply to _all queue')
        #checkbox.show()
        #msg_area.set_text_and_icon(gtk.STOCK_DIALOG_ERROR, 'Access Denied',                                    msg, checkbox)

        #msg_area.connect("response", self.OnMessageAreaReponse, msg_area)
        #msg_area.connect("close", self.OnMessageAreaClose, msg_area)
        vbox.pack_start(msg_area, False, False)
        #msg_area.show()
        


    # This bit of code constructs a list of methods for binding to Gtk+
    # signals. This way, we don't have to maintain a list manually,
    # saving editing effort. It's enough to add a method to the suitable
    # class and give the same name in the .glade file.

    def __getattr__(self, attribute):
        """Allow direct use of window widget."""
        widget = self.builder.get_object(attribute)
        if widget is None:
            raise AttributeError('Widget \'%s\' not found' % attribute)
        self.__dict__[attribute] = widget # cache result
        return widget

    def close(self, *args):
        debug('closing...')
        self.filelist.abort()
        self.converter.abort()
        self.widget.hide_all()
        self.widget.destroy()
        # wait one second...
        # yes, this sucks badly, but signals can still be called by gstreamer
        #  so wait a bit for things to calm down, and quit.
        gtk_sleep(1)
        gtk.main_quit()
        return True

    on_window_delete_event = close
    on_quit_activate = close
    on_quit_button_clicked = close

    def on_add_activate(self, *args):
        last_folder = self.prefs.get_string('last-used-folder')
        if last_folder:
            self.addchooser.set_current_folder_uri(last_folder)

        ret = self.addchooser.run()
        folder = self.addchooser.get_current_folder_uri()
        self.addchooser.hide()
        if ret == gtk.RESPONSE_OK and folder:
            self.filelist.add_uris(self.addchooser.get_uris())
            self.prefs.set_string('last-used-folder', folder)
        self.set_sensitive()

    def on_addfolder_activate(self, *args):
        last_folder = self.prefs.get_string('last-used-folder')
        if last_folder:
            self.addfolderchooser.set_current_folder_uri(last_folder)

        ret = self.addfolderchooser.run()
        folders = self.addfolderchooser.get_uris()
        folder = self.addfolderchooser.get_current_folder_uri()
        self.addfolderchooser.hide()
        if ret == gtk.RESPONSE_OK:
            extensions = None
            if self.combo.get_active():
                patterns = filepattern[self.combo.get_active()][1].split(';')
                extensions = [os.path.splitext(p)[1] for p in patterns]
            self.filelist.add_uris(folders, extensions=extensions)
            if folder:
                self.prefs.set_string('last-used-folder', folder)

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
        self.set_sensitive()
        self.set_status()

    def on_progress(self):
        if self.pulse_progress > 0: # still waiting for tags
            self.set_progress(self.pulse_progress, display_time=False)
            return True
        if self.pulse_progress == -1: # still waiting for add
            self.set_progress()
            return True
        if self.pulse_progress == False: # conversion ended
            return False

        perfile = {}
        for s in self.filelist.get_files():
            perfile[s] = None
        running, progress = self.converter.get_progress(perfile)

        if running:
            self.set_progress(progress)
            for sound_file, taskprogress in perfile.iteritems():
                if taskprogress > 0.0:
                    sound_file.progress = taskprogress
                    self.set_file_progress(sound_file, taskprogress)
                if taskprogress is None and sound_file.progress:
                    self.set_file_progress(sound_file, 1.0)
                    sound_file.progress = None
        return running

    def do_convert(self):
        self.pulse_progress = -1
        gobject.timeout_add(100, self.on_progress)
        self.progressbar.set_text(_('Preparing conversion...'))
        files = self.filelist.get_files()
        total = len(files)
        for i, sound_file in enumerate(files):
            gtk_iteration()
            self.pulse_progress = float(i)/total # TODO: still needed?
            sound_file.progress = None
            self.converter.add(sound_file)
        # all was OK
        self.set_status('')
        self.pulse_progress = None
        self.converter.start()
        self.set_sensitive()

    def on_convert_button_clicked(self, *args):
        # reset and show progress bar
        self.set_progress(0)
        self.progress_frame.show()
        self.status_frame.hide()
        self.progress_time = time.time()
        self.set_progress()
        self.set_status(_('Converting'))
        for soundfile in self.filelist.get_files():
            self.set_file_progress(soundfile, 0.0)
        # start conversion
        self.do_convert()
        # update ui
        self.set_sensitive()

    def on_button_pause_clicked(self, *args):
        self.converter.toggle_pause(not self.converter.paused)
            
        if self.converter.paused:
            self.current_pause_start = time.time()
        else:
            self.paused_time += time.time() - self.current_pause_start

    def on_button_cancel_clicked(self, *args):
        self.converter.abort()
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
        #TODO: about.set_property('translator_credits', TRANSLATORS)
        about.show()

    def on_aboutdialog_response(self, *args):
        self.aboutdialog.hide()

    def selection_changed(self, *args):
        self.set_sensitive()

    def conversion_ended(self):
        self.pulse_progress = False
        self.progress_frame.hide()
        self.filelist.hide_row_progress()
        self.status_frame.show()
        self.widget.set_sensitive(True)
        try:
            from gi.repository import Unity
            launcher = Unity.LauncherEntry.get_for_desktop_id ("soundconverter.desktop")
            launcher.set_property("progress_visible", False)
        except ImportError:
            pass


    def set_widget_sensitive(self, name, sensitivity):
        self.sensitive_widgets[name].set_sensitive(sensitivity)

    def set_sensitive(self):
        """update the sensitive state of UI for the current state"""
        for w in self.unsensitive_when_converting:
            self.set_widget_sensitive(w, not self.converter.running)

        if not self.converter.running:
            self.set_widget_sensitive('remove',
                self.filelist_selection.count_selected_rows() > 0)
            self.set_widget_sensitive('convert_button',
                                        self.filelist.is_nonempty())

    def set_file_progress(self, sound_file, progress):
        row = sound_file.filelist_row
        self.filelist.set_row_progress(row, progress)

    def set_progress(self, fraction=None, display_time=True):
        if not fraction:
            if fraction is None:
                self.progressbar.pulse()
            else:
                self.progressbar.set_fraction(0)
                self.progressbar.set_text('')
            self.progressfile.set_markup('')
            self.filelist.hide_row_progress()
            return

        if self.converter.paused:
            self.progressbar.set_text(_('Paused'))
            return

        fraction = min(max(fraction, 0.0), 1.0)
        self.progressbar.set_fraction(fraction)
            
        if display_time:
            t = time.time() - self.converter.run_start_time - \
                              self.paused_time
            if (t < 1):
                # wait a bit not to display crap
                self.progressbar.pulse()
                return

            r = (t / fraction - t)
            s = max(r % 60, 1)
            m = r / 60

            remaining = _('%d:%02d left') % (m, s)
            self.progressbar.set_text(remaining)
            self.progress_time = time.time()

    def set_status(self, text=None):
        if not text:
            text = _('Ready')
        self.statustext.set_markup(text)
        gtk_iteration()

    def is_active(self):
        return self.widget.is_active()


NAME = VERSION = None
win = None

def gui_main(name, version, gladefile, input_files):
    global NAME, VERSION
    NAME, VERSION = name, version
    gnome.init(name, version)
    builder = gtk.Builder()
    builder.set_translation_domain(name.lower())
    builder.add_from_file(gladefile)

    global win
    win = SoundConverterWindow(builder)
    import error
    error.set_error_handler(ErrorDialog(builder))
    
    #error_dialog = MsgAreaErrorDialog(builder)
    #error_dialog.msg_area = win.msg_area
    #error.set_error_handler(error_dialog)

    gobject.idle_add(win.filelist.add_uris, input_files)
    win.set_sensitive()
    gtk.main()
