## Process this file with automake to produce Makefile.in

#AUTOMAKE_OPTIONS = dist-bzip2

SUBDIRS = po src data doc

CLEANFILES=

EXTRA_DIST = intltool-extract.in intltool-merge.in intltool-update.in autogen.sh
DISTCLEANFILES = intltool-extract intltool-merge intltool-update


release:
	echo svn -m "release $(VERSION)" copy . svn+ssh://kassoulet@svn.berlios.de/svnroot/repos/soundconverter/tags/release-$(VERSION)
	echo lftp -c "open ftp.berlios.de/incoming ; put soundconverter-$(VERSION).tar.gz"

