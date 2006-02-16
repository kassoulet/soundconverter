Summary: GNOME Sound Convertion.
Name: soundconverter
Version: 0.8.4
Release: 1
License: GPL
BuildArch: noarch
Group: Applications/Multimedia
Source: http://
URL: http://soundconverter.berlios.de
Packager: Gautier Portet < kassoulet users.berlios.de >
Requires: python, pygtk2, pygtk2-libglade TODO
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot-%(%{__id_u})

%description
SoundConverter is a GNOME GStreamer sound converter. It is written in Python and uses the PyGTK toolkit.

%prep
%setup -n %{name}

%build
#soundconverter is a Python script

%install
make install

%clean
make uninstall

%postun
#Leave nothing behind
rm -Rf /usr/share/%{name}
rm -Rf /usr/bin/%{name}

%files
/usr/bin/soundconverter
/usr/share/soundconverter/soundconverter.glade
/usr/share/soundconverter/soundconverter.py

%changelog

