## Process this file with automake to produce Makefile.in

AUTOMAKE_OPTIONS = dist-bzip2

SUBDIRS = po soundconverter bin data doc

CLEANFILES=

EXTRA_DIST = autogen.sh
DISTCLEANFILES = intltool-extract.in intltool-merge.in intltool-update.in intltool-extract intltool-merge intltool-update


release: dist
	echo git tag -a $(VERSION)
	echo git push --tags 
	echo lp-project-upload soundconverter $(VERSION) soundconverter-$(VERSION).tar.bz2

# generate the changelog from git log
changelog:
	git log 3fd8.. --pretty --numstat --summary | ./git2cl.pl > ChangeLog
	cat ChangeLog.old >> ChangeLog
