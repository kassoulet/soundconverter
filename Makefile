#
# (c) 2005 Gautier Portet
#

PACKAGE=soundconverter
VERSION=0.8.0

prefix = /usr/local
bindir = $(prefix)/bin
sharedir = $(prefix)/share/soundconverter

all:

check:
	python soundconverterTests.py
	if [ -d snd ]; then python soundconverter.py -t snd/* > /dev/null; fi

lint:
	pylint --enable-format=n --no-docstring-rgx=.\* soundconverter.py

install:
	install -d $(DESTDIR)$(bindir) $(DESTDIR)$(sharedir)
	install -m 0644 soundconverter.glade $(DESTDIR)$(sharedir)
	install -m 0644 logo.png $(DESTDIR)$(sharedir)
	sed 's,^GLADE *=.*,GLADE = "$(sharedir)/soundconverter.glade",' \
	soundconverter.py > make-install-temp
	install make-install-temp $(DESTDIR)$(bindir)/soundconverter
	rm make-install-temp

clean:
	rm -f *.pyc *.bak
    
dist:
	mkdir -p $(PACKAGE)-$(VERSION)
	cp -a ChangeLog README soundconverter.py TODO soundconverter.glade soundconverter.gladep Makefile logo.png COPYING soundconverter.1 soundconverterTests.py $(PACKAGE)-$(VERSION)
	mkdir -p $(PACKAGE)-$(VERSION)/po
	cp -a po/fr.po $(PACKAGE)-$(VERSION)/po
	cp -a po/pl.po $(PACKAGE)-$(VERSION)/po	
	tar czf $(PACKAGE)-$(VERSION).tar.gz $(PACKAGE)-$(VERSION)
	rm -rf $(PACKAGE)-$(VERSION)

commit:
	svn commit

release:
	svn -m "release $(VERSION)" copy . svn+ssh://kassoulet@svn.berlios.de/svnroot/repos/soundconverter/tags/release-$(VERSION)
	lftp -c "open ftp.berlios.de/incoming ; put soundconverter-$(VERSION).tar.gz"
