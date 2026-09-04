
project(
  'fedora-nova',
  version: '0.7.2-dev',
  meson_version: '>= 1.2.0',
  default_options: [
    'warning_level=2',
  ],
)

gnome = import('gnome')
python = import('python').find_installation('python3')

dependency('gtk4', version: '>= 4.10')
dependency('libadwaita-1', version: '>= 1.4')

prefix = get_option('prefix')
datadir = get_option('datadir')
pkgdatadir = join_paths(prefix, datadir, 'fedora-nova')
app_id = 'io.github.fedoranova.FedoraNova.Devel'

subdir('src')
subdir('data')

install_subdir(
  'core',
  install_dir: pkgdatadir,
  exclude_directories: [
    'themes-src',
    'scripts/__pycache__',
  ],
  exclude_files: [
    'SHA256SUMS',
    'scripts/build-theme-sass.sh',
    'scripts/preview_reload.py',
  ],
)

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
