import sys
import pathlib
import pkg_resources

DESKTOP = """[Desktop Entry]
Type=Application
Name=ris_widget
Exec={bin_dir}/ris_widget %F
Icon={desktop_dir}/ris_widget.svg
MimeType=image/png;image/tiff;
Categories=Utility;
"""

def install_desktop_file(desktop_dir):
    desktop_dir = pathlib.Path(desktop_dir)
    desktop_dir.mkdir(exist_ok=True)
    icon = pkg_resources.resource_string(__name__, 'icon.svg').decode('utf-8')
    with (desktop_dir / 'ris_widget.svg').open('w') as iconfile:
        iconfile.write(icon)
    bin_dir = pathlib.Path(sys.argv[0]).parent
    with (desktop_dir / 'ris_widget.desktop').open('w') as out:
        out.write(DESKTOP.format(bin_dir=bin_dir, desktop_dir=desktop_dir))