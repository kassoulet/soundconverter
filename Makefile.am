## Process this file with automake to produce Makefile.in

AUTOMAKE_OPTIONS = dist-xz no-dist-gzip

SUBDIRS = bin soundconverter data doc po

CLEANFILES=

EXTRA_DIST = autogen.sh
DISTCLEANFILES = intltool-extract.in intltool-merge.in intltool-update.in intltool-extract intltool-merge intltool-update

README: README.rst

release: changelog dist
	echo git tag -a $(VERSION) -m release-$(VERSION)
	echo git push --tags 
	echo lp-project-upload soundconverter $(VERSION) soundconverter-$(VERSION).tar.xz

# generate the changelog from git log
changelog:
	git log 3fd8.. --pretty --numstat --summary | ./git2cl.pl > ChangeLog
	cat ChangeLog.old >> ChangeLog

test:
	PYTHONPATH=. python3 tests/unittests.py 
