prefix = /usr/local
bindir = $(prefix)/bin
sharedir = $(prefix)/share/soundconverter

all:

check:
	python soundconverterTests.py
	if [ -d snd ]; then python soundconverter.py -t snd/* > /dev/null; fi

install:
	install -d $(bindir) $(sharedir)
	install -m 0644 soundconverter.glade $(sharedir)
	sed 's,^GLADE *=.*,GLADE = "$(sharedir)/soundconverter.glade",' \
	    soundconverter.py > make-install-temp
	install make-install-temp $(bindir)/soundconverter
	rm make-install-temp

clean:
	rm -f *.pyc
