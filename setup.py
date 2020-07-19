from distutils.core import setup

# TODO how is https://github.com/xfce-mirror/catfish installed
# and https://github.com/bluesabre/menulibre

# TODO figure out how to build a .deb from this
# how to install the latest source globally? 

setup(
    name='soundconverter',
    version='3.0.2',
    description=(
        'A simple sound converter application for the GNOME environment. '
        'It writes WAV, FLAC, MP3, and Ogg Vorbis files.'
    ),
    license='GPL-3.0',
    packages=['soundconverter'],

    data_files=[
        ('share/soundconverter/', ['data/soundconverter.glade']),
        ('share/soundconverter/', ['data/soundconverter-logo.svg']),
        ('share/metainfo/', ['data/soundconverter.appdata.xml'])
    ],
)
