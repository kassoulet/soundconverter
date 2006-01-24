#
# (c) 2005-2006 Gautier Portet
#

PACKAGE=soundconverter
VERSION=0.8.3

LINGUAS=fr pl pt_BR

PO_FILES=$(patsubst %,po/%.po, $(LINGUAS))
MO_FILES=$(patsubst %.po,%.mo, $(PO_FILES))
TRANSLATABLE_FILES=soundconverter.py soundconverter.glade

RELEASE_NAME=$(PACKAGE)-$(VERSION)

prefix = /usr/local
bindir = $(prefix)/bin
sharedir = $(prefix)/share/soundconverter

POT_FILE=po/soundconverter.pot

all: 
	

lang: $(MO_FILES)
	

$(POT_FILE): $(TRANSLATABLE_FILES)
	xgettext $(TRANSLATABLE_FILES) -o $(POT_FILE) 

$(PO_FILES): $(POT_FILE)
	msgmerge -U $@ $(POT_FILE)

$(MO_FILES): $(PO_FILES)
	msgfmt $< -o $@
	
check:
	python soundconverterTests.py
	if [ -d snd ]; then python soundconverter.py -t snd/* > /dev/null; fi

lint:
	pylint --enable-format=n --no-docstring-rgx=.\* soundconverter.py

install:
	install -d $(DESTDIR)$(bindir) $(DESTDIR)$(sharedir)
	install -m 0644 soundconverter.glade $(DESTDIR)$(sharedir)
	install -m 0644 logo.png $(DESTDIR)$(sharedir)
	install -m 0644 po/fr.mo    ${DESTDIR}${prefix}/share/locale/fr/LC_MESSAGES/soundconverter.mo
	install -m 0644 po/pl.mo    ${DESTDIR}${prefix}/share/locale/pl/LC_MESSAGES/soundconverter.mo
	install -m 0644 po/pt_BR.mo ${DESTDIR}${prefix}/share/locale/pt-BR/LC_MESSAGES/soundconverter.mo
	sed 's,^GLADE *=.*,GLADE = "$(sharedir)/soundconverter.glade",' \
	soundconverter.py > make-install-temp
	install make-install-temp $(DESTDIR)$(bindir)/soundconverter
	rm make-install-temp

install-local:
	install -d ~/bin ~/share/soundconverter
	install -m 0644 soundconverter.glade ~/share/soundconverter
	install -m 0644 logo.png ~/share/soundconverter
	sed 's,^GLADE *=.*,GLADE = "~/share/soundconverter/soundconverter.glade",' \
	soundconverter.py > make-install-temp
	install make-install-temp ~/bin/soundconverter
	rm make-install-temp

clean:
	rm -f *.pyc *.bak
    
dist:
	mkdir -p $(RELEASE_NAME)
	cp -a ChangeLog README soundconverter.py TODO soundconverter.glade soundconverter.gladep Makefile logo.png COPYING soundconverter.1 soundconverterTests.py $(DEST)
	mkdir -p $(RELEASE_NAME)/po
	cp -a $(PO_FILES) $(MO_FILES) $(RELEASE_NAME)/po
	tar czf $(RELEASE_NAME).tar.gz $(RELEASE_NAME)
	rm -rf $(RELEASE_NAME)

commit:
	svn commit

release:
	svn -m "release $(VERSION)" copy . svn+ssh://kassoulet@svn.berlios.de/svnroot/repos/soundconverter/tags/release-$(VERSION)
	lftp -c "open ftp.berlios.de/incoming ; put soundconverter-$(VERSION).tar.gz"
