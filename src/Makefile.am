## Process this file with automake to produce Makefile.in

appdir = $(bindir)
app_SCRIPTS = soundconverter

CLEANFILES = soundconverter

soundconverter: soundconverter.py
	sed -e s!\@datadir\@!$(datadir)! -e s!\@version\@!$(VERSION)! < $< > $@
	chmod +x $@

EXTRA_DIST = soundconverterTests.py
