#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# SoundConverter - GNOME application for converting between audio formats.
# Copyright 2004 Lars Wirzenius
# Copyright 2005-2010 Gautier Portet
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
from urlparse import urlparse
from gettext import gettext as _

import gobject
import gst
import gnomevfs
import gtk # TODO
import gconf

from fileoperations import vfs_encode_filename, file_encode_filename
from fileoperations import unquote_filename, vfs_makedirs, vfs_unlink
from fileoperations import vfs_exists
from fileoperations import use_gnomevfs
from task import BackgroundTask
from queue import TaskQueue
from utils import debug, log
from settings import mime_whitelist
from error import SoundConverterException
from error import show_error
from notify import notification

required_elements = ('decodebin', 'fakesink', 'audioconvert', 'typefind')
for element in required_elements:
    if not gst.element_factory_find(element):
        print "required gstreamer element \'%s\' not found." % element
        sys.exit(1)


if gst.element_factory_find('giosrc'):
    gstreamer_source = 'giosrc'
    gstreamer_sink = 'giosink'
    encode_filename = vfs_encode_filename
    use_gnomevfs = True
    print '  using gio'
elif gst.element_factory_find('gnomevfssrc'):
    gstreamer_source = 'gnomevfssrc'
    gstreamer_sink = 'gnomevfssink'
    encode_filename = vfs_encode_filename
    use_gnomevfs = True
    print '  using deprecated gnomevfssrc'
else:
    gstreamer_source = 'filesrc'
    gstreamer_sink = 'filesink'
    encode_filename = file_encode_filename
    print '  not using gnomevfssrc, look for a gnomevfs gstreamer package.'


encoders = (
    ('flacenc',   'FLAC'),
    ('wavenc',    'WAV'),
    ('vorbisenc', 'Ogg Vorbis'),
    ('oggmux',    'Ogg Vorbis'),
    ('id3v2mux',  'MP3 Tags'),
    ('xingmux',   'Xing Header'),
    ('lame',      'MP3'),
    ('faac',      'AAC'),
    ('mp4mux',    'AAC'),
    )

available_elements = {}

for encoder, name in encoders:
    have_it = bool(gst.element_factory_find(encoder))
    if have_it:
        available_elements[encoder] = True
    else:
        print ("\t'%s' gstreamer element not found"
            ", disabling %s." % (encoder, name))

if 'oggmux' not in available_elements:
    del available_elements['vorbisenc']


# load gstreamer audio profiles
_GCONF_PROFILE_PATH = "/system/gstreamer/0.10/audio/profiles/"
_GCONF_PROFILE_LIST_PATH = "/system/gstreamer/0.10/audio/global/profile_list"
audio_profiles_list = []
audio_profiles_dict = {}

_GCONF = gconf.client_get_default()
profiles = _GCONF.get_list(_GCONF_PROFILE_LIST_PATH, 1)
for name in profiles:
    if (_GCONF.get_bool(_GCONF_PROFILE_PATH + name + "/active")):
        description = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/name")
        extension = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/extension")
        pipeline = _GCONF.get_string(_GCONF_PROFILE_PATH + name + "/pipeline")
        profile = description, extension, pipeline
        audio_profiles_list.append(profile)
        audio_profiles_dict[description] = profile


class Pipeline(BackgroundTask):

    """A background task for running a GstPipeline."""

    def __init__(self):
        BackgroundTask.__init__(self)
        self.pipeline = None
        self.sound_file = None
        self.command = []
        self.parsed = False
        self.signals = []
        self.processing = False
        self.eos = False
        self.error = None
        self.connected_signals = []

    def started(self):
        self.play()

    def finished(self):
        for element, sid in self.connected_signals:
            element.disconnect(sid)
        self.stop_pipeline()

    def abort(self):
        self.finished()

    def add_command(self, command):
        self.command.append(command)

    def add_signal(self, name, signal, callback):
        self.signals.append((name, signal, callback,))

    def toggle_pause(self, paused):
        if not self.pipeline:
            debug('toggle_pause(): pipeline is None !')
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
        self.done()
        if result == gst.pbutils.INSTALL_PLUGINS_USER_ABORT:
            dialog = gtk.MessageDialog(parent=None, flags=gtk.DIALOG_MODAL,
                type=gtk.MESSAGE_INFO,
                buttons=gtk.BUTTONS_OK,
                message_format='Plugin installation aborted.')
            dialog.run()
            dialog.hide()
            return

        show_error('Error', 'failed to install plugins: %s' % gobject.markup_escape_text(str(result)))

    def on_error(self, error):
        self.error = error
        log('error: %s (%s)' % (error, self.command))

    def on_message(self, bus, message):
        t = message.type
        import gst
        if t == gst.MESSAGE_ERROR:
            error, debug = message.parse_error()
            self.eos = True
            self.on_error(error)
            self.done()

        elif t == gst.MESSAGE_ELEMENT:
            st = message.structure
            if st and st.get_name().startswith('missing-'):
                self.pipeline.set_state(gst.STATE_NULL)
                if gst.pygst_version >= (0, 10, 10):
                    import gst.pbutils
                    detail = gst.pbutils.\
                        missing_plugin_message_get_installer_detail(message)
                    ctx = gst.pbutils.InstallPluginsContext()
                    gst.pbutils.install_plugins_async([detail], ctx,
                                                        self.install_plugin_cb)

        elif t == gst.MESSAGE_EOS:
            self.eos = True
            self.done()

        elif t == gst.MESSAGE_TAG:
            self.found_tag(self, '', message.parse_tag())
        return True

    def play(self):
        if not self.parsed:
            command = ' ! '.join(self.command)
            debug('launching: \'%s\'' % command)
            try:
                self.pipeline = gst.parse_launch(command)
                bus = self.pipeline.get_bus()
                assert not self.connected_signals
                self.connected_signals = []
                for name, signal, callback in self.signals:
                    if name:
                        element = self.pipeline.get_by_name(name)
                    else:
                        element = bus
                    sid = element.connect(signal, callback)
                    self.connected_signals.append((element, sid,))

                self.parsed = True
                del self.command
                del self.signals
            except gobject.GError, e:
                show_error('GStreamer error when creating pipeline', str(e))
                self.error = str(e)
                self.eos = True
                self.done()
                return

        bus.add_signal_watch()
        watch_id = bus.connect('message', self.on_message)
        self.watch_id = watch_id

        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop_pipeline(self):
        if not self.pipeline:
            debug('pipeline already stopped!')
            return
        bus = self.pipeline.get_bus()
        bus.disconnect(self.watch_id)
        bus.remove_signal_watch()
        self.pipeline.set_state(gst.STATE_NULL)
        self.pipeline = None

    def get_position(self):
        return NotImplementedError


class TypeFinder(Pipeline):

    def __init__(self, sound_file):
        Pipeline.__init__(self)
        self.sound_file = sound_file

        command = '%s location="%s" ! typefind name=typefinder ! fakesink' % \
            (gstreamer_source, encode_filename(self.sound_file.uri))
        self.add_command(command)
        self.add_signal('typefinder', 'have-type', self.have_type)

    def on_error(self, error):
        self.error = error
        log('error: %s (%s)' % (error, self.sound_file.filename_for_display))

    def set_found_type_hook(self, found_type_hook):
        self.found_type_hook = found_type_hook

    def have_type(self, typefind, probability, caps):
        mime_type = caps.to_string()
        debug('have_type:', mime_type,
                                self.sound_file.filename_for_display)
        self.sound_file.mime_type = None
        #self.sound_file.mime_type = mime_type
        for t in mime_whitelist:
            if t in mime_type:
                self.sound_file.mime_type = mime_type
        if not self.sound_file.mime_type:
            log('Mime type skipped: %s' % mime_type)
        self.pipeline.set_state(gst.STATE_NULL)
        self.done()

    def finished(self):
        Pipeline.finished(self)
        if self.error:
            return
        if self.found_type_hook and self.sound_file.mime_type:
            gobject.idle_add(self.found_type_hook, self.sound_file,
                                self.sound_file.mime_type)
            self.sound_file.mime_type = True # remove string


class Decoder(Pipeline):

    """A GstPipeline background task that decodes data and finds tags."""

    def __init__(self, sound_file):
        Pipeline.__init__(self)
        self.sound_file = sound_file
        self.time = 0
        self.position = 0
        self.probe_id = None

        command = '%s location="%s" name=src ! decodebin name=decoder' % \
            (gstreamer_source, encode_filename(self.sound_file.uri))
        self.add_command(command)
        self.add_signal('decoder', 'new-decoded-pad', self.new_decoded_pad)

    def on_error(self, error):
        self.error = error
        log('error: %s (%s)' % (error,
            self.sound_file.filename_for_display))

    def have_type(self, typefind, probability, caps):
        pass

    def query_duration(self):
        try:
            if not self.sound_file.duration and self.pipeline:
                self.sound_file.duration = self.pipeline.query_duration(
                                            gst.FORMAT_TIME)[0] / gst.SECOND
                debug('got file duration:', self.sound_file.duration)
        except gst.QueryError:
            pass

    def found_tag(self, decoder, something, taglist):
        debug('found_tags:', self.sound_file.filename_for_display)
        for k in taglist.keys():
            debug('\t%s=%s' % (k, taglist[k]))
            if isinstance(taglist[k], gst.Date):
                taglist['year'] = taglist[k].year
                taglist['date'] = '%04d-%02d-%02d' % (taglist[k].year,
                                    taglist[k].month, taglist[k].day)
        tag_whitelist = (
            'artist',
            'album',
            'title',
            'track-number',
            'track-count',
            'genre',
            'date',
            'year',
            'timestamp',
        )
        tags = {}
        for k in taglist.keys():
            if k in tag_whitelist:
                tags[k] = taglist[k]

        #print tags
        self.sound_file.tags.update(tags)
        self.sound_file.have_tags = True

        try:
            self.sound_file.duration = self.pipeline.query_duration(
                                            gst.FORMAT_TIME)[0] / gst.SECOND
        except gst.QueryError:
            pass

    def _buffer_probe(self, pad, buffer):
        """buffer probe callback used to get real time
           since the beginning of the stream"""
        if buffer.timestamp == gst.CLOCK_TIME_NONE:
            debug('removing buffer probe')
            pad.remove_buffer_probe(self.probe_id)
            return False

        self.position = float(buffer.timestamp) / gst.SECOND

        return True

    def new_decoded_pad(self, decoder, pad, is_last):
        """ called when a decoded pad is created """
        self.probe_id = pad.add_buffer_probe(self._buffer_probe)
        self.probed_pad = pad
        self.processing = True
        self.query_duration()

    def finished(self):
        if self.probe_id:
            self.probed_pad.remove_buffer_probe(self.probe_id)
        Pipeline.finished(self)

    def get_sound_file(self):
        return self.sound_file

    def get_input_uri(self):
        return self.sound_file.uri

    def get_duration(self):
        """ return the total duration of the sound file """
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
        self.add_command('fakesink')
        self.add_signal(None, 'message::state-changed', self.on_state_changed)
        self.tagread = False

    def set_found_tag_hook(self, found_tag_hook):
        self.found_tag_hook = found_tag_hook

    def on_state_changed(self, bus, message):
        prev, new, pending = message.parse_state_changed()
        if new == gst.STATE_PLAYING and not self.tagread:
            self.tagread = True
            debug('TagReading done...')
            self.done()

    def finished(self):
        Pipeline.finished(self)
        self.sound_file.tags_read = True
        if self.found_tag_hook:
            gobject.idle_add(self.found_tag_hook, self)


class Converter(Decoder):

    """A background task for converting files to another format."""

    def __init__(self, sound_file, output_filename, output_type,
                    delete_original=False, output_resample=False,
                    resample_rate=48000, force_mono=False):
        Decoder.__init__(self, sound_file)

        self.converting = True

        self.output_filename = output_filename
        self.output_type = output_type
        self.vorbis_quality = None
        self.aac_quality = None
        self.mp3_bitrate = None
        self.mp3_mode = None
        self.mp3_quality = None

        self.output_resample = output_resample
        self.resample_rate = resample_rate
        self.force_mono = force_mono

        self.overwrite = False
        self.delete_original = delete_original

        self.got_duration = False

    def init(self):
        self.encoders = {
            'audio/x-vorbis': self.add_oggvorbis_encoder,
            'audio/x-flac': self.add_flac_encoder,
            'audio/x-wav': self.add_wav_encoder,
            'audio/mpeg': self.add_mp3_encoder,
            'audio/x-m4a': self.add_aac_encoder,
            'gst-profile': self.add_audio_profile,
        }

        self.add_command('audioconvert')

        # audio resampling support
        if self.output_resample:
            self.add_command('audioresample ! rate=%d ! audioconvert' %
                     (self.resample_rate))

        if self.force_mono:
            self.add_command('audioresample ! channels=1 ! audioconvert')

        encoder = self.encoders[self.output_type]()
        if not encoder:
            # TODO: add proper error management when an encoder cannot be created
            dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL,
                        gtk.MESSAGE_ERROR,
                        gtk.BUTTONS_OK,
                        _("Cannot create a decoder for \'%s\' format.") % \
                        self.output_type)
            dialog.run()
            dialog.hide()
            return

        self.add_command(encoder)

        uri = gnomevfs.URI(self.output_filename)
        dirname = uri.parent
        if dirname and not gnomevfs.exists(dirname):
            log('Creating folder: \'%s\'' % dirname)
            if not vfs_makedirs(str(dirname)):
                # TODO add better error management
                dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL,
                            gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_OK,
                            _("Cannot create \'%s\' folder.") % \
                            dirname)
                dialog.run()
                dialog.hide()
                return

        self.add_command('%s location="%s"' % (
            gstreamer_sink, encode_filename(self.output_filename)))
        if self.overwrite and vfs_exists(self.output_filename):
            log('overwriting \'%s\'' % self.output_filename)
            vfs_unlink(self.output_filename)

    def finished(self):
        self.converting = False
        Pipeline.finished(self)

        # Copy file permissions
        try:
            info = gnomevfs.get_file_info(self.sound_file.uri,
                                        gnomevfs.FILE_INFO_FIELDS_PERMISSIONS)
            gnomevfs.set_file_info(self.output_filename, info,
                                            gnomevfs.SET_FILE_INFO_PERMISSIONS)
        except:
            log('Cannot set permission on \'%s\'' %
                        gnomevfs.format_uri_for_display(self.output_filename))

        if self.delete_original and self.processing and not self.error:
            log('deleting: \'%s\'' % self.sound_file.uri)
            try:
                gnomevfs.unlink(self.sound_file.uri)
            except:
                log('Cannot remove \'%s\'' %
                        gnomevfs.format_uri_for_display(self.output_filename))

    def on_error(self, err):
        #pass

        show_error('<b>%s</b>' % _('GStreamer Error:'), '%s\n<i>(%s)</i>' % (err,
                    self.sound_file.filename_for_display))

    def set_vorbis_quality(self, quality):
        self.vorbis_quality = quality

    def set_aac_quality(self, quality):
        self.aac_quality = quality

    def set_mp3_mode(self, mode):
        self.mp3_mode = mode

    def set_mp3_quality(self, quality):
        self.mp3_quality = quality

    def set_flac_compression(self, compression):
        self.flac_compression = compression

    def set_wav_sample_width(self, sample_width):
        self.wav_sample_width = sample_width

    def set_audio_profile(self, audio_profile):
        self.audio_profile = audio_profile

    def add_flac_encoder(self):
        s = 'flacenc mid-side-stereo=true quality=%s' % self.flac_compression
        return s

    def add_wav_encoder(self):
        return 'audio/x-raw-int,width=%d ! audioconvert ! wavenc' % (
                self.wav_sample_width)

    def add_oggvorbis_encoder(self):
        cmd = 'vorbisenc'
        if self.vorbis_quality is not None:
            cmd += ' quality=%s' % self.vorbis_quality
        cmd += ' ! oggmux '
        return cmd

    def add_mp3_encoder(self):

        cmd = 'lame quality=2 '

        if self.mp3_mode is not None:
            properties = {
                'cbr' : (0, 'bitrate'),
                'abr' : (3, 'vbr-mean-bitrate'),
                'vbr' : (4, 'vbr-quality')
            }

            cmd += 'vbr=%s ' % properties[self.mp3_mode][0]
            if self.mp3_quality == 9:
                # GStreamer set max bitrate to 320 but lame uses
                # mpeg2 with vbr-quality==9, so max bitrate is 160
                # - update: now set to 128 since lame don't accept 160 anymore.
                cmd += 'vbr-max-bitrate=128 '
            elif properties[self.mp3_mode][0]:
                cmd += 'vbr-max-bitrate=320 '
            cmd += '%s=%s ' % (properties[self.mp3_mode][1], self.mp3_quality)

            if available_elements['xingmux'] and properties[self.mp3_mode][0]:
                # add xing header when creating VBR mp3
                cmd += '! xingmux '

        if available_elements['id3v2mux']:
            # add tags
            cmd += '! id3v2mux '

        return cmd

    def add_aac_encoder(self):
        return 'faac profile=2 bitrate=%s ! mp4mux' % (self.aac_quality * 1000)

    def add_audio_profile(self):
        pipeline = audio_profiles_dict[self.audio_profile][2]
        return pipeline


class ConverterQueueCanceled(SoundConverterException):

    """Exception thrown when a ConverterQueue is canceled."""

    def __init__(self):
        SoundConverterException.__init__(self, _('Conversion Canceled'), '')

class ConverterQueueError(SoundConverterException):

    """Exception thrown when a ConverterQueue had an error."""

    def __init__(self):
        SoundConverterException.__init__(self, _('Conversion Error'), '')


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
        self.errors = []
        self.error_count = 0

    def add(self, sound_file):
        output_filename = self.window.prefs.generate_filename(sound_file)
        path = urlparse(output_filename) [2]
        path = unquote_filename(path)

        exists = True
        try:
            gnomevfs.get_file_info(gnomevfs.URI((output_filename)))
        except gnomevfs.NotFoundError:
            exists = False
        except gnomevfs.AccessDeniedError:
            self.error_count += 1
            msg = _('Access denied: \'%s\'' % output_filename)
            #show_error(msg, '')
            raise ConverterQueueError()
            return
        except:
            self.error_count += 1
            log('Invalid URI: \'%s\'' % output_filename)
            raise ConverterQueueError()
            return

        # do not overwrite source file !!
        if output_filename == sound_file.uri:
            self.error_count += 1
            show_error(_('Cannot overwrite source file(s)!'), '')
            raise ConverterQueueCanceled()

        if exists:
            if self.overwrite_action != None:
                result = self.overwrite_action
            else:
                dialog = self.window.existsdialog

                dpath = os.path.basename(path)
                dpath = gobject.markup_escape_text(dpath)

                msg = \
                _('The output file <i>%s</i>\n exists already.\n '\
                    'Do you want to skip the file, overwrite it or'\
                    ' cancel the conversion?\n') % dpath

                dialog.message.set_markup(msg)
                dialog.set_transient_for(self.window.widget)

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
                        self.window.prefs.get_string('output-mime-type'),
                        self.window.prefs.get_int('delete-original'),
                        self.window.prefs.get_int('output-resample'),
                        self.window.prefs.get_int('resample-rate'),
                        self.window.prefs.get_int('force-mono'),
                        )
        c.set_vorbis_quality(self.window.prefs.get_float('vorbis-quality'))
        c.set_aac_quality(self.window.prefs.get_int('aac-quality'))
        c.set_flac_compression(self.window.prefs.get_int('flac-compression'))
        c.set_wav_sample_width(self.window.prefs.get_int('wav-sample-width'))
        c.set_audio_profile(self.window.prefs.get_string('audio-profile'))

        quality = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }
        mode = self.window.prefs.get_string('mp3-mode')
        c.set_mp3_mode(mode)
        c.set_mp3_quality(self.window.prefs.get_int(quality[mode]))
        c.init()
        self.add_task(c)
        c.add_listener('finished', self.on_task_finished)
        #c.got_duration = False
        #self.total_duration += c.get_duration()
        gobject.timeout_add(1000, self.set_progress)
        self.all_tasks = None

    def get_progress(self, task):
        return (self.duration_processed +
                    task.get_position()) / self.total_duration

    def set_progress(self, tasks=None):

        tasks = self.running_tasks
        filename = ''
        if tasks and tasks[0]:
            filename = tasks[0].sound_file.filename_for_display

        # try to get all tasks durations
        total_duration = self.total_duration
        if not self.all_tasks:
            self.all_tasks = []
            self.all_tasks.extend(self.waiting_tasks)
            self.all_tasks.extend(self.running_tasks)
            #self.all_tasks.extend(self.finished_tasks)

        for task in self.all_tasks:
            if not task.got_duration:
                duration = task.sound_file.duration
                if duration:
                    self.total_duration += duration
                    task.got_duration = True
                else:
                    total_duration = 0

        from ui import win
        position = 0.0
        s = []
        prolist = []
        for task in range(self.finished_tasks):
            prolist.append(1.0)
        for task in tasks:
            if task.converting:
                position += task.get_position()
                taskprogress = float(task.get_position()) / task.sound_file.duration if task.sound_file.duration else 0
                prolist.append(taskprogress)
                self.window.set_file_progress(task.sound_file, taskprogress)
        for task in self.waiting_tasks:
            prolist.append(0.0)

        progress = sum(prolist)/len(prolist)
        self.window.set_progress(progress, 1.0, filename)
        return self.running

    def on_task_finished(self, task):
        self.duration_processed += task.get_duration()
        self.errors.append(task.error)
        if task.error:
            self.error_count += 1

    def finished(self):
        #print 'ConverterQueue.finished', self
        if self.running_tasks:
            print self.running_tasks
            raise NotImplementedError
        TaskQueue.finished(self)
        self.window.set_progress(0, 0)
        self.window.set_sensitive()
        self.window.conversion_ended()
        total_time = self.run_finish_time - self.run_start_time
        msg = _('Conversion done, in %s') % self.format_time(total_time)
        if self.error_count:
            msg += ', %d error(s)' % self.error_count
        self.window.set_status(msg)
        if not self.window.is_active():
            notification(msg)
        self.reset_counters()

    def format_time(self, seconds):
        units = [(86400, 'd'),
                 (3600, 'h'),
                 (60, 'm'),
                 (1, 's')]
        seconds = round(seconds)
        result = []
        for factor, unity in units:
            count = int(seconds / factor)
            seconds -= count * factor
            if count > 0 or (factor == 1 and not result):
                result.append('%d %s' % (count, unity))
        assert seconds == 0
        return ' '.join(result)

    def abort(self):
        TaskQueue.abort(self)
        self.window.set_progress(0, 0)
        self.window.set_sensitive()
        self.reset_counters()
