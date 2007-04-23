## Process this file with automake to produce Makefile.in

gladedir = $(DESTDIR)$(datadir)/soundconverter
dist_glade_DATA = soundconverter.glade soundconverter-logo.svg

icondir = $(DESTDIR)$(datadir)/icons/hicolor/48x48/apps
dist_icon_DATA = soundconverter.png

svgicondir = $(DESTDIR)$(datadir)/icons/hicolor/scalable/apps
dist_svgicon_DATA = soundconverter.svg


gtk_update_icon_cache = gtk-update-icon-cache -f -t $(datadir)/icons/hicolor

install-data-hook: update-icon-cache
uninstall-hook: update-icon-cache
update-icon-cache:
	@-if test -z "$(DESTDIR)"; then \
		echo "Updating Gtk icon cache."; \
		$(gtk_update_icon_cache); \
	else \
		echo "*** Icon cache not updated.  After (un)install, run this:"; \
		echo "***   $(gtk_update_icon_cache)"; \
	fi


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
