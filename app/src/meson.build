
launcher_conf = configuration_data()
launcher_conf.set('PYTHON', python.full_path())
launcher_conf.set('PKGDATADIR', pkgdatadir)

configure_file(
  input: 'fedora-nova-settings-devel.in',
  output: 'fedora-nova-settings-devel',
  configuration: launcher_conf,
  install: true,
  install_dir: get_option('bindir'),
)

install_subdir(
  'fedora_nova',
  install_dir: pkgdatadir,
  exclude_directories: ['__pycache__'],
)
