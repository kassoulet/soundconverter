    ## Process this file with automake to produce Makefile.in

gladedir = $(datadir)/soundconverter
dist_glade_DATA = soundconverter.glade soundconverter-logo.svg

icondir = $(datadir)/icons/hicolor/48x48/apps
dist_icon_DATA = soundconverter.png

svgicondir = $(datadir)/icons/hicolor/scalable/apps
dist_svgicon_DATA = soundconverter.svg


gtk_update_icon_cache = gtk-update-icon-cache -f -t $(datadir)/icons/hicolor

install-data-hook: update-icon-cache
uninstall-hook: update-icon-cache
update-icon-cache:  
	@-if test -z "$(datadir)"; then \
		echo "Updating Gtk icon cache."; \
		$(gtk_update_icon_cache); \
	else \
		echo "*** Icon cache not updated.  After (un)install, run this:"; \
		echo "***   $(gtk_update_icon_cache)"; \
	fi

desktop_in_files= soundconverter.desktop.in
desktop_files=$(desktop_in_files:.desktop.in=.desktop)
@INTLTOOL_DESKTOP_RULE@

gsettings_SCHEMAS = org.soundconverter.gschema.xml
@GSETTINGS_RULES@

Applicationsdir = $(datadir)/applications
Applications_DATA = $(desktop_files)

appdatadir = $(datadir)/metainfo
dist_appdata_DATA = soundconverter.appdata.xml

EXTRA_DIST = $(desktop_in_files) $(desktop_files) $(gsettings_SCHEMAS)

DISTCLEANFILES = $(desktop_files)
