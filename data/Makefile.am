## Process this file with automake to produce Makefile.in

gladedir = $(datadir)/soundconverter
dist_glade_DATA = soundconverter-logo.png soundconverter.glade 

pixmapsdir = $(datadir)/pixmaps
pixmaps_DATA = soundconverter-icon.png

icondir = $(datadir)/soundconverter
icon_DATA = soundconverter-icon.png

desktop_in_files= soundconverter.desktop.in

desktop_files=$(desktop_in_files:.desktop.in=.desktop)
@INTLTOOL_DESKTOP_RULE@

Applicationsdir = $(datadir)/applications
Applications_DATA = $(desktop_files)

EXTRA_DIST = soundconverter.gladep \
        $(desktop_in_files)     \
        $(desktop_files)

DISTCLEANFILES = $(desktop_files)
