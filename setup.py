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

    # TODO remove this before making a PR:
    # this isn't used currently, but it would allow to read the
    # contents of our data files: https://stackoverflow.com/a/5899643
    package_data={'soundconverter': ['data/*']},
)
