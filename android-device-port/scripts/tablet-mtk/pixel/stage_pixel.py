#!/usr/bin/env python3
"""Unpack chosen NikGapps (Android 16) packages into a staging tree laid out like /system/product.

usage: stage_pixel.py NikGapps-full-arm64-16-*.zip OUT_DIR [Name ...]    (names: see PACKS; default = all PACKS keys)
NikGapps stores each app as AppSet/<set>/<App>.zip holding files whose names are paths with '___' for '/', e.g.
'___priv-app___NexusLauncherRelease/x.apk' -> priv-app/NexusLauncherRelease/x.apk. Nothing here is Google-redistributable: run it on your own copy."""
import io, os, sys, zipfile

PACKS = {   # name -> AppSet path inside the NikGapps zip
    'PixelLauncher': 'PixelSpecifics/PixelLauncher', 'GoogleWallpaper': 'PixelSpecifics/GoogleWallpaper', 'PixelThemes': 'PixelSpecifics/PixelThemes',
    'SettingsServices': 'PixelSpecifics/SettingsServices', 'DevicePersonalizationServices': 'PixelSpecifics/DevicePersonalizationServices',
    'PrivateComputeServices': 'PixelSpecifics/PrivateComputeServices', 'EmojiWallpaper': 'PixelSpecifics/EmojiWallpaper',
    'QuickAccessWallet': 'PixelSpecifics/QuickAccessWallet', 'PixelWeather': 'PixelSpecifics/PixelWeather', 'GoogleSounds': 'GoogleSounds/GoogleSounds',
    'GBoard': 'GBoard/GBoard', 'GoogleClock': 'GoogleClock/GoogleClock', 'GoogleCalendar': 'GoogleCalendar/GoogleCalendar', 'GoogleCalculator': 'GoogleCalculator/GoogleCalculator',
    'GoogleContacts': 'GoogleContacts/GoogleContacts', 'GoogleDialer': 'GoogleDialer/GoogleDialer', 'GoogleMessages': 'GoogleMessages/GoogleMessages',
    'GoogleFiles': 'GoogleFiles/GoogleFiles', 'DocumentsUIGoogle': 'GoogleFiles/DocumentsUIGoogle', 'StorageManager': 'GoogleFiles/StorageManager',
}

SKIP = ('/overlay/', '/usr/srec/', '/usr/share/', 'preinstalled-packages-platform-overlays.xml')   # static overlays and offline-speech data are left out

def stage(nik_zip, out, names, skip=SKIP):
    z = zipfile.ZipFile(nik_zip)
    for n in names:
        inner = zipfile.ZipFile(io.BytesIO(z.read(f'AppSet/{PACKS[n]}.zip')))
        for m in inner.infolist():
            if m.is_dir() or not m.filename.startswith('___'): continue     # installer.sh / uninstaller.sh stay behind
            dst0 = m.filename.replace('___', '/')
            if any(k in dst0 for k in skip): continue
            dst = os.path.join(out, m.filename.replace('___', '/').lstrip('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as f: f.write(inner.read(m))
            print(f'{n}: {dst[len(out):]}')

if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    stage(sys.argv[1], sys.argv[2], sys.argv[3:] or list(PACKS))
