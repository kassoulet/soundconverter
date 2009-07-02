## Process this file with automake to produce Makefile.in

AUTOMAKE_OPTIONS = dist-bzip2

SUBDIRS = po src data doc

CLEANFILES=

EXTRA_DIST = autogen.sh
DISTCLEANFILES = intltool-extract.in intltool-merge.in intltool-update.in intltool-extract intltool-merge intltool-update


release: dist
	svn -m "release $(VERSION)" copy . svn+ssh://kassoulet@svn.berlios.de/svnroot/repos/soundconverter/tags/release-$(VERSION)
	lftp -c "open ftp.berlios.de/incoming ; put soundconverter-$(VERSION).tar.gz"

