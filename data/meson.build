
desktop_file = configure_file(
  input: 'io.github.fedoranova.FedoraNova.Devel.desktop.in',
  output: 'io.github.fedoranova.FedoraNova.Devel.desktop',
  copy: true,
)

install_data(
  desktop_file,
  install_dir: join_paths(get_option('datadir'), 'applications'),
)

install_data(
  'io.github.fedoranova.FedoraNova.Devel.metainfo.xml',
  install_dir: join_paths(get_option('datadir'), 'metainfo'),
)

install_data(
  'io.github.fedoranova.FedoraNova.Devel.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0', 'schemas'),
)

install_data(
  'io.github.fedoranova.FedoraNova.Devel.svg',
  install_dir: join_paths(
    get_option('datadir'),
    'icons',
    'hicolor',
    'scalable',
    'apps',
  ),
)
