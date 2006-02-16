## Process this file with automake to produce Makefile.in

appdir = $(bindir)
app_SCRIPTS = soundconverter

#gladedir = $(datadir)/soundconverter
#dist_glade_DATA = soundconverter.png soundconverter.glade 

#pixmapsdir = $(datadir)/pixmaps
#pixmaps_DATA = soundconverter-icon.png

#EXTRA_DIST = soundconverter.gladep soundconverter.py
CLEANFILES = soundconverter

soundconverter: soundconverter.py
	sed -e s!\@datadir\@!$(gladedir)! -e s!\@version\@!$(VERSION)! < $< > $@
	chmod +x $@
