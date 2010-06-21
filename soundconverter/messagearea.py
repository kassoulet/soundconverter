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

# THIS FILE WAS PART OF THE JOKOSHER PROJECT AND LICENSED UNDER THE GPL.

import gtk
import gobject


class MessageArea(gtk.HBox):

    __gsignals__ = {
        "response"  : ( gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_INT,) ),
        "close"     : ( gobject.SIGNAL_RUN_LAST | gobject.SIGNAL_ACTION, gobject.TYPE_NONE, () )
    }

    def __init__(self):
        gtk.HBox.__init__(self)

        self.contents = None
        self.changing_style = False

        self.main_hbox = gtk.HBox(False, 16) # FIXME: use style properties
        self.main_hbox.show()
        self.main_hbox.set_border_width(8) # FIXME: use style properties

        self.action_area = gtk.VBox(True, 3) # FIXME: use style properties */
        self.action_area.show()

        self.main_hbox.pack_end(self.action_area, False, True)
        self.pack_start(self.main_hbox, True, True)

        self.set_app_paintable(True)

        self.connect("expose-event", self.paint_message_area)
        self.connect("size-allocate", self.on_size_allocate)

        # Note that we connect to style-set on one of the internal
        # widgets, not on the message area itself, since gtk does
        # not deliver any further style-set signals for a widget on
        # which the style has been forced with gtk_widget_set_style()
        self.main_hbox.connect("style-set", self.style_set)

    def on_size_allocate(self, widget, rectangle):
        # force a _complete_ redraw here or else in certain cases after resizing
        # some border lines are left painted on top of the main content area.
        self.queue_draw()

    def style_set(self, widget, prev_style):
        if self.changing_style:
            return

        # This is a hack needed to use the tooltip background color
        window = gtk.Window(gtk.WINDOW_POPUP)
        window.set_name("gtk-tooltip")
        window.ensure_style()
        style = window.get_style()

        self.changing_style = True
        self.set_style(style)
        self.changing_style = False

        window.destroy()

        self.queue_draw()

    def paint_message_area(self, widget, event):
        a = widget.get_allocation()
        x = a.x + 1
        y = a.y + 1
        width = a.width - 2
        height = a.height - 2
        widget.style.paint_flat_box(widget.window, gtk.STATE_NORMAL, gtk.SHADOW_OUT, None,
                                    widget, "tooltip", x, y, width, height)
        return False

    def action_widget_activated(self, widget):
        resp = self.get_response_data(widget)
        if resp is None:
            resp = gtk.RESPONSE_NONE
        self.response(resp)

    def get_response_data(self, widget):
        return widget.get_data("gedit-message-area-response-data")

    def set_response_data(self, widget, new_id):
        widget.set_data("gedit-message-area-response-data", new_id)

    def add_action_widget(self, child, response_id):
        self.set_response_data(child, response_id)

        try:
            signal = child.get_activate_signal()
        except ValueError:
            signal = None

        if isinstance(child, gtk.Button):
            child.connect("clicked", self.action_widget_activated)
        elif signal:
            child.connect(signal, self.action_widget_activated)
        else:
            pass
            #g_warning("Only 'activatable' widgets can be packed into the action area of a GeditMessageArea");

        if response_id != gtk.RESPONSE_HELP:
            self.action_area.pack_end(child, False, False)
        else:
            self.action_area.pack_start(child, False, False)


    def add_button(self, text, response_id):
        button = gtk.Button(stock=text)
        button.set_flags(gtk.CAN_DEFAULT)
        button.show()
        self.add_action_widget(button, response_id)
        return button

    def add_buttons(self, *buttons):
        for text, response_id in buttons:
            self.add_button(text, response_id)

    def set_response_sensitive(self, response_id, setting):
        children = self.action_area.get_children()

        for child in children:
            rd = self.get_response_data(child)
            if rd == response_id:
                child.set_sensitive(setting)

    def set_default_response(self, response_id):
        children = self.action_area.get_children()

        for child in children:
            rd = self.get_response_data(child)
            if rd == response_id:
                child.grab_default()

    def response(self, response_id):
        self.emit("response", response_id)

    def add_stock_button_with_text(self, text, stock_id, response_id):
        button = gtk.Button(text, use_underline=True)
        button.set_image(gtk.image_new_from_stock(stock_id,gtk.ICON_SIZE_BUTTON))
        button.set_flags(gtk.CAN_DEFAULT)
        button.show()
        self.add_action_widget(button, response_id)

    def set_contents(self, contents):
        self.contents = contents;
        self.main_hbox.pack_start(self.contents, True, True)

    def set_text_and_icon(self, icon_stock_id, primary_text,
                            secondary_text=None, additionnal_widget=None):
        hbox_content = gtk.HBox(False, 8)
        hbox_content.show()

        image = gtk.image_new_from_stock(icon_stock_id, gtk.ICON_SIZE_DIALOG)
        image.show()
        hbox_content.pack_start(image, False, False)
        image.set_alignment(0.5, 0.5)

        vbox = gtk.VBox(False, 6)
        vbox.show()
        hbox_content.pack_start(vbox, True, True)

        primary_markup = "<b>%s</b>" % primary_text
        primary_label = gtk.Label(primary_markup)
        primary_label.set_use_markup(True)
        primary_label.set_line_wrap(True)
        primary_label.set_alignment(0, 0.5)
        primary_label.set_flags(gtk.CAN_FOCUS)
        primary_label.set_selectable(True)
        primary_label.show()

        vbox.pack_start(primary_label, True, True)

        if secondary_text:
            secondary_markup = "<small>%s</small>" % secondary_text
            secondary_label = gtk.Label(secondary_markup)
            secondary_label.set_flags(gtk.CAN_FOCUS)
            secondary_label.set_use_markup(True)
            secondary_label.set_line_wrap(True)
            secondary_label.set_selectable(True)
            secondary_label.set_alignment(0, 0.5)
            secondary_label.show()

            vbox.pack_start(secondary_label, True, True)

        if additionnal_widget:
            vbox.pack_start(additionnal_widget, True, True)

        self.set_contents(hbox_content)


gtk.binding_entry_add_signal(MessageArea, gtk.gdk.keyval_from_name("Escape"), 0, "close")


