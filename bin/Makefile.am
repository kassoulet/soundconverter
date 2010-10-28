bin_SCRIPTS = \
	soundconverter

CLEANFILES = $(bin_SCRIPTS)

soundconverter: soundconverter.py
	sed -e s!\@datadir\@!$(datadir)!  -e s!\@libdir\@!$(libdir)!  -e s!\@version\@!$(VERSION)! < $< > $@
	chmod +x $@


