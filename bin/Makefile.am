bin_SCRIPTS = \
	soundconverter

EXTRA_DIST = soundconverter.py
CLEANFILES = $(bin_SCRIPTS)

soundconverter: soundconverter.py
	sed -e s!\@datadir\@!$(datadir)!  -e s!\@libdir\@!$(libdir)!  -e s!\@version\@!$(VERSION)! < $< > $@
	chmod +x $@


