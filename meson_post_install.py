#!/usr/bin/env python3

import os
import subprocess

def main():
    if 'DESTDIR' in os.environ:
        print('DESTDIR is set, not running post-install script')
        return

    print('Running post-install script...')

    # Compile GSettings schemas
    gschema_dir = os.path.join(os.environ['MESON_INSTALL_DESTDIR_PREFIX'], 'share', 'glib-2.0', 'schemas')
    if os.path.isdir(gschema_dir):
        print(f'Compiling GSettings schemas in {gschema_dir}...')
        subprocess.run(['glib-compile-schemas', gschema_dir], check=True)

    # Update desktop database
    apps_dir = os.path.join(os.environ['MESON_INSTALL_DESTDIR_PREFIX'], 'share', 'applications')
    if os.path.isdir(apps_dir):
        print(f'Updating desktop database in {apps_dir}...')
        subprocess.run(['update-desktop-database', '-q', apps_dir], check=True)

if __name__ == '__main__':
    main()
