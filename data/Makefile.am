## Process this file with automake to produce Makefile.in

gladedir = $(DESTDIR)$(datadir)/soundconverter
dist_glade_DATA = soundconverter.glade soundconverter-logo.svg

icondir = $(DESTDIR)$(datadir)/icons/hicolor/scalable/apps
dist_icon_DATA = soundconverter.svg

#pixmapsdir = $(DESTDIR)$(datadir)/pixmaps
#pixmaps_DATA = soundconverter.png

desktop_in_files= soundconverter.desktop.in

desktop_files=$(desktop_in_files:.desktop.in=.desktop)
@INTLTOOL_DESKTOP_RULE@

Applicationsdir = $(DESTDIR)$(datadir)/applications
Applications_DATA = $(desktop_files)

EXTRA_DIST = soundconverter.gladep \
        $(desktop_in_files)     \
        $(desktop_files)

DISTCLEANFILES = $(desktop_files)
