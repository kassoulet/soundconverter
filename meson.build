project('soundconverter', version : '4.1.1', license : 'GPL3+', meson_version : '>= 0.59.0', default_options : [ 'warning_level=2', 'buildtype=debugoptimized', ])

python = import('python')

py_inst = python.find_installation('python3')

gnome = import('gnome')
i18n = import('i18n')

project_description = 'A simple sound converter application for the GNOME environment. It writes WAV, FLAC, MP3, Opus, WMA and Ogg Vorbis files.'

subdir('po')


# Executable
install_data(['run'], install_dir: get_option('bindir'))

# Appstream
install_data(
  ['data/soundconverter.appdata.xml'],
  install_dir: join_paths(get_option('datadir'), 'metainfo')
)
update_desktop_database = find_program('update-desktop-database', required : false)
if update_desktop_database.found()
  meson.add_install_script('meson_post_install.py')
endif

# Gschema
gschema_dir = join_paths(get_option('datadir'), 'glib-2.0', 'schemas')
install_data(
  'data/org.soundconverter.gschema.xml',
  install_dir: gschema_dir
)
compile_schemas = find_program('glib-compile-schemas', required : false)
if compile_schemas.found()
  meson.add_install_script('meson_post_install.py')
endif

# Icons
install_data(
  'data/soundconverter.png',
  install_dir: join_paths(get_option('datadir'), 'pixmaps')
)
install_data(
  'data/soundconverter.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps')
)

# man page
#install_man('data/soundconverter.1')

# desktop file
desktop_file = i18n.merge_file(
  input : 'data/soundconverter.desktop.in',
  output : 'soundconverter.desktop',
    po_dir : join_paths(meson.project_source_root(), 'po'),
  type : 'desktop',
  install : true,
  install_dir : join_paths(get_option('datadir'), 'applications')
)

# GtkBuilder files
install_data(
  ['data/soundconverter.ui'],
  install_dir: join_paths(get_option('datadir'), 'soundconverter')
)

# Install python files
py_inst.install_sources(
  ['soundconverter/__init__.py',
   'soundconverter/common/constants.py',
   'soundconverter/common/__init__.py',
   'soundconverter/gstreamer/converter.py',
   'soundconverter/gstreamer/discoverer.py',
   'soundconverter/gstreamer/__init__.py',
   'soundconverter/interface/batch.py',
   'soundconverter/interface/filelist.py',
   'soundconverter/interface/gladewindow.py',
   'soundconverter/interface/mainloop.py',
   'soundconverter/interface/notify.py',
   'soundconverter/interface/preferences.py',
   'soundconverter/interface/theme.py',
   'soundconverter/interface/ui.py',
   'soundconverter/interface/__init__.py',
   'soundconverter/util/error.py',
   'soundconverter/util/fileoperations.py',
   'soundconverter/util/formats.py',
   'soundconverter/util/formatting.py',
   'soundconverter/util/logger.py',
   'soundconverter/util/namegenerator.py',
   'soundconverter/util/settings.py',
   'soundconverter/util/soundfile.py',
   'soundconverter/util/task.py',
   'soundconverter/util/taskqueue.py',
   'soundconverter/util/__init__.py'],
  subdir: 'soundconverter'
)

install_data(
  'bin/soundconverter',
  install_dir: get_option('bindir'),
  rename: ['soundconverter']
)

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true
)