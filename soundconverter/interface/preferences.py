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

import urllib.request
import urllib.parse
import urllib.error
from gettext import gettext as _

from gi.repository import Gtk, GLib

from soundconverter.util.fileoperations import filename_to_uri, \
    beautify_uri
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.settings import get_gio_settings
from soundconverter.util.formats import get_quality, \
    get_bitrate_from_settings, get_file_extension
from soundconverter.util.namegenerator import TargetNameGenerator, \
    subfolder_patterns, basename_patterns, locale_patterns_dict
from soundconverter.util.logger import logger
from soundconverter.gstreamer.converter import available_elements
from soundconverter.interface.gladewindow import GladeWindow


encoders = (
    ('audio/x-vorbis', 'vorbisenc'),
    ('audio/mpeg', 'lamemp3enc'),
    ('audio/x-flac', 'flacenc'),
    ('audio/x-wav', 'wavenc'),
    ('audio/x-m4a', 'fdkaacenc,faac,avenc_aac'),
    ('audio/ogg; codecs=opus', 'opusenc'),
)  # must be in same order as the output_mime_type GtkComboBox


class PreferencesDialog(GladeWindow):
    sensitive_names = [
        'vorbis_quality', 'choose_folder', 'create_subfolders',
        'subfolder_pattern', 'jobs_spinbutton', 'resample_hbox',
        'force_mono'
    ]

    def __init__(self, builder, parent):
        self.settings = get_gio_settings()
        GladeWindow.__init__(self, builder)

        # encoders should be in the same order as in the glade file
        for i, encoder in enumerate(encoders):
            extension = get_file_extension(encoder[0])
            ui_row_text = self.liststore8[i][0]
            # the extension should be part of the row with the correct index
            assert extension.lower() in ui_row_text.lower()

        self.dialog = builder.get_object('prefsdialog')
        self.dialog.set_transient_for(parent)
        self.example = builder.get_object('example_filename')
        self.force_mono = builder.get_object('force_mono')

        self.target_bitrate = None

        self.sensitive_widgets = {}
        for name in self.sensitive_names:
            self.sensitive_widgets[name] = builder.get_object(name)
            assert self.sensitive_widgets[name] is not None

        self.encoders = None
        self.present_mime_types = []

        self.set_widget_initial_values()
        self.set_sensitive()

        tip = [_('Available patterns:')]
        for k in sorted(locale_patterns_dict.values()):
            tip.append(k)
        self.custom_filename.set_tooltip_text('\n'.join(tip))

    def set_widget_initial_values(self):
        self.quality_tabs.set_show_tabs(False)

        if self.settings.get_boolean('same-folder-as-input'):
            widget = self.same_folder_as_input
        else:
            widget = self.into_selected_folder
        widget.set_active(True)

        self.target_folder_chooser = Gtk.FileChooserDialog(
            title=_('Add Folder…'),
            transient_for=self.dialog,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )

        self.target_folder_chooser.add_button(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL
        )
        self.target_folder_chooser.add_button(
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        self.target_folder_chooser.set_select_multiple(False)
        self.target_folder_chooser.set_local_only(False)

        uri = filename_to_uri(urllib.parse.quote(
            self.settings.get_string('selected-folder'), safe='/:@'
        ))
        self.target_folder_chooser.set_uri(uri)
        self.update_selected_folder()

        widget = self.create_subfolders
        widget.set_active(self.settings.get_boolean('create-subfolders'))

        widget = self.subfolder_pattern
        active = self.settings.get_int('subfolder-pattern-index')
        model = widget.get_model()
        model.clear()
        for pattern, desc in subfolder_patterns:
            i = model.append()
            model.set(i, 0, desc)
        widget.set_active(active)

        if self.settings.get_boolean('replace-messy-chars'):
            widget = self.replace_messy_chars
            widget.set_active(True)

        if self.settings.get_boolean('delete-original'):
            self.delete_original.set_active(True)

        current_mime_type = self.settings.get_string('output-mime-type')

        # deactivate output if encoder plugin is not present
        widget = self.output_mime_type
        model = widget.get_model()
        assert len(model) == len(encoders), 'model:{} widgets:{}'.format(
            len(model), len(encoders)
        )

        i = 0
        model = self.output_mime_type.get_model()
        for mime, encoder_name in encoders:
            # valid default output?
            encoder_present = any(
                e in available_elements for e in encoder_name.split(',')
            )
            if encoder_present:
                # add to supported outputs
                self.present_mime_types.append(mime)
                i += 1
            else:
                logger.error(
                    '{} {} is not supported, a gstreamer plugins package '
                    'is possibly missing.'.format(mime, encoder_name)
                )
                del model[i]

        for i, mime in enumerate(self.present_mime_types):
            if current_mime_type == mime:
                widget.set_active(i)
        self.change_mime_type(current_mime_type)

        # display information about mp3 encoding
        if 'lamemp3enc' not in available_elements:
            widget = self.lame_absent
            widget.show()

        widget = self.vorbis_quality
        quality = self.settings.get_double('vorbis-quality')
        quality_setting = get_quality('audio/x-vorbis', quality, reverse=True)
        widget.set_active(-1)
        self.vorbis_quality.set_active(quality_setting)
        if self.settings.get_boolean('vorbis-oga-extension'):
            self.vorbis_oga_extension.set_active(True)

        widget = self.aac_quality
        quality = self.settings.get_int('aac-quality')
        quality_setting = get_quality('audio/x-m4a', quality, reverse=True)
        widget.set_active(quality_setting)

        widget = self.opus_quality
        quality = self.settings.get_int('opus-bitrate')
        quality_setting = get_quality('audio/ogg; codecs=opus', quality, reverse=True)
        widget.set_active(quality_setting)

        widget = self.flac_compression
        quality = self.settings.get_int('flac-compression')
        quality_setting = get_quality('audio/x-flac', quality, reverse=True)
        widget.set_active(quality_setting)

        widget = self.wav_sample_width
        quality = self.settings.get_int('wav-sample-width')
        quality_setting = get_quality('audio/x-wav', quality, reverse=True)
        widget.set_active(quality_setting)

        self.mp3_quality = self.mp3_quality
        self.mp3_mode = self.mp3_mode

        mode = self.settings.get_string('mp3-mode')
        self.change_mp3_mode(mode)

        widget = self.basename_pattern
        active = self.settings.get_int('name-pattern-index')
        model = widget.get_model()
        model.clear()
        for pattern, desc in basename_patterns:
            iter = model.append()
            model.set(iter, 0, desc)
        widget.set_active(active)

        self.custom_filename.set_text(
            self.settings.get_string('custom-filename-pattern')
        )
        if self.basename_pattern.get_active() == len(basename_patterns)-1:
            self.custom_filename_box.set_sensitive(True)
        else:
            self.custom_filename_box.set_sensitive(False)

        output_resample = self.settings.get_boolean('output-resample')
        self.resample_toggle.set_active(output_resample)

        cell = Gtk.CellRendererText()
        self.resample_rate.pack_start(cell, True)
        self.resample_rate.add_attribute(cell, 'text', 0)
        rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000, 128000]
        rate = self.settings.get_int('resample-rate')
        try:
            idx = rates.index(rate)
        except ValueError:
            idx = -1
        self.resample_rate.set_active(idx)

        self.force_mono.set_active(self.settings.get_boolean('force-mono'))

        self.jobs.set_active(self.settings.get_boolean('limit-jobs'))
        self.jobs_spinbutton.set_value(self.settings.get_int('number-of-jobs'))

        self.update_example()

    def update_selected_folder(self):
        self.into_selected_folder.set_use_underline(False)
        self.into_selected_folder.set_label(
            _('Into folder %s') %
            beautify_uri(self.settings.get_string('selected-folder'))
        )

    def update_example(self):
        """Refresh the example in the settings dialog."""
        sound_file = SoundFile('file:///foo/bar.flac')
        sound_file.tags.update({
            'track-number': 1,
            'track-count': 99,
            'album-disc-number': 2,
            'album-disc-count': 9
        })
        sound_file.tags.update(locale_patterns_dict)

        generator = TargetNameGenerator()
        generator.replace_messy_chars = False

        example_path = GLib.markup_escape_text(
            generator.generate_target_uri(sound_file, for_display=True)
        )
        position = 0
        replaces = []

        while True:
            beginning = example_path.find('{', position)
            if beginning == -1:
                break
            end = example_path.find('}', beginning)

            tag = example_path[beginning:end+1]
            available_tags = [
                v.lower() for v in list(locale_patterns_dict.values())
            ]
            if tag.lower() in available_tags:
                bold_tag = tag.replace(
                    '{', '<b>{'
                ).replace(
                    '}', '}</b>'
                )
                replaces.append([tag, bold_tag])
            else:
                red_tag = tag.replace(
                    '{', '<span foreground=\'red\'><i>{'
                ).replace(
                    '}', '}</i></span>'
                )
                replaces.append([tag, red_tag])
            position = beginning + 1

        for tag, formatted in replaces:
            example_path = example_path.replace(tag, formatted)

        self.example.set_markup(example_path)

        markup = '<small>{}</small>'.format(
            _('Target bitrate: %s') % get_bitrate_from_settings()
        )
        self.approx_bitrate.set_markup(markup)

    def set_sensitive(self):
        for widget in list(self.sensitive_widgets.values()):
            widget.set_sensitive(False)

        same_folder = self.settings.get_boolean('same-folder-as-input')
        for name in ['choose_folder', 'create_subfolders',
                     'subfolder_pattern']:
            self.sensitive_widgets[name].set_sensitive(not same_folder)

        self.sensitive_widgets['vorbis_quality'].set_sensitive(
            self.settings.get_string('output-mime-type') == 'audio/x-vorbis')

        self.sensitive_widgets['jobs_spinbutton'].set_sensitive(
            self.settings.get_boolean('limit-jobs'))

        self.sensitive_widgets['resample_hbox'].set_sensitive(True)
        self.sensitive_widgets['force_mono'].set_sensitive(True)

    def run(self):
        self.dialog.run()
        self.dialog.hide()

    def on_delete_original_toggled(self, button):
        self.settings.set_boolean('delete-original', button.get_active())

    def on_same_folder_as_input_toggled(self, button):
        self.settings.set_boolean('same-folder-as-input', True)
        self.set_sensitive()
        self.update_example()

    def on_into_selected_folder_toggled(self, button):
        self.settings.set_boolean('same-folder-as-input', False)
        self.set_sensitive()
        self.update_example()

    def on_choose_folder_clicked(self, button):
        ret = self.target_folder_chooser.run()
        folder = self.target_folder_chooser.get_uri()
        self.target_folder_chooser.hide()
        if ret == Gtk.ResponseType.OK:
            if folder:
                folder = urllib.parse.unquote(folder)
                self.settings.set_string('selected-folder', folder)
                self.update_selected_folder()
                self.update_example()

    def on_create_subfolders_toggled(self, button):
        self.settings.set_boolean('create-subfolders', button.get_active())
        self.update_example()

    def on_subfolder_pattern_changed(self, combobox):
        self.settings.set_int('subfolder-pattern-index', combobox.get_active())
        self.update_example()

    def on_basename_pattern_changed(self, combobox):
        self.settings.set_int('name-pattern-index', combobox.get_active())
        if combobox.get_active() == len(basename_patterns)-1:
            self.custom_filename_box.set_sensitive(True)
        else:
            self.custom_filename_box.set_sensitive(False)
        self.update_example()

    def on_custom_filename_changed(self, entry):
        self.settings.set_string('custom-filename-pattern', entry.get_text())
        self.update_example()

    def on_replace_messy_chars_toggled(self, button):
        self.settings.set_boolean('replace-messy-chars', button.get_active())

    def change_mime_type(self, mime_type):
        """Show the correct quality tab based on the selected format."""
        self.settings.set_string('output-mime-type', mime_type)
        self.set_sensitive()
        self.update_example()
        tabs = {
            'audio/x-vorbis': 0,
            'audio/mpeg': 1,
            'audio/x-flac': 2,
            'audio/x-wav': 3,
            'audio/x-m4a': 4,
            'audio/ogg; codecs=opus': 5,
        }
        self.quality_tabs.set_current_page(tabs[mime_type])

    def on_output_mime_type_changed(self, combo):
        """Called when the format is changed on the UI."""
        format_index = combo.get_active()
        mime = encoders[format_index][0]
        if mime in self.present_mime_types:
            self.change_mime_type(mime)

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
            return  # just de-selectionning
        fquality = get_quality('audio/x-vorbis', combobox.get_active())
        self.settings.set_double('vorbis-quality', fquality)
        self.update_example()

    def on_vorbis_oga_extension_toggled(self, toggle):
        self.settings.set_boolean('vorbis-oga-extension', toggle.get_active())
        self.update_example()

    def on_aac_quality_changed(self, combobox):
        quality = get_quality('audio/x-m4a', combobox.get_active())
        self.settings.set_int('aac-quality', quality)
        self.update_example()

    def on_opus_quality_changed(self, combobox):
        quality = get_quality('audio/ogg; codecs=opus', combobox.get_active())
        self.settings.set_int('opus-bitrate', quality)
        self.update_example()

    def on_wav_sample_width_changed(self, combobox):
        quality = get_quality('audio/x-wav', combobox.get_active())
        self.settings.set_int('wav-sample-width', quality)
        self.update_example()

    def on_flac_compression_changed(self, combobox):
        quality = get_quality('audio/x-flac', combobox.get_active())
        self.settings.set_int('flac-compression', quality)
        self.update_example()

    def on_force_mono_toggle(self, button):
        self.settings.set_boolean('force-mono', button.get_active())
        self.update_example()

    def change_mp3_mode(self, mode):
        keys = {'cbr': 0, 'abr': 1, 'vbr': 2}
        self.mp3_mode.set_active(keys[mode])

        keys = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality',
        }
        quality = self.settings.get_int(keys[mode])

        index = get_quality('audio/mpeg', quality, mode, reverse=True)
        self.mp3_quality.set_active(index)
        self.update_example()

    def on_mp3_mode_changed(self, combobox):
        mode = ('cbr', 'abr', 'vbr')[combobox.get_active()]
        self.settings.set_string('mp3-mode', mode)
        self.change_mp3_mode(mode)

    def on_mp3_quality_changed(self, combobox):
        keys = {
            'cbr': 'mp3-cbr-quality',
            'abr': 'mp3-abr-quality',
            'vbr': 'mp3-vbr-quality'
        }
        mode = self.settings.get_string('mp3-mode')

        bitrate = get_quality('audio/mpeg', combobox.get_active(), mode)
        self.settings.set_int(keys[mode], bitrate)
        self.update_example()

    def on_resample_rate_changed(self, combobox):
        selected = combobox.get_active()
        rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000, 128000]
        self.settings.set_int('resample-rate', rates[selected])
        self.update_example()

    def on_resample_toggle(self, rstoggle):
        self.settings.set_boolean('output-resample', rstoggle.get_active())
        self.resample_rate.set_sensitive(rstoggle.get_active())
        self.update_example()

    def on_jobs_toggled(self, jtoggle):
        self.settings.set_boolean('limit-jobs', jtoggle.get_active())
        self.jobs_spinbutton.set_sensitive(jtoggle.get_active())

    def on_jobs_spinbutton_value_changed(self, jspinbutton):
        self.settings.set_int('number-of-jobs', int(jspinbutton.get_value()))

