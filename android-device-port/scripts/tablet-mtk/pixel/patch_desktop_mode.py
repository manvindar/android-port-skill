#!/usr/bin/env python3
"""Pixel Launcher <-> SystemUI: the IDesktopMode shell interface differs between the launcher's build and this GSI (setTaskbarIconPositionLocator
-> 'Parcel data not fully consumed' -> launcher crash). This tablet has no desktop mode, so never keep the shell's IDesktopMode binder:
SystemUiProxy.desktopMode stays null and every desktop call is already guarded by a null check.
usage: patch_desktop_mode.py APKTOOL_DECODED_DIR"""
import glob, sys
for p in glob.glob(sys.argv[1] + '/smali*/com/android/quickstep/SystemUiProxy.smali'):
    s = open(p).read()
    old = "    :goto_8\n    iput-object v0, p0, Lcom/android/quickstep/SystemUiProxy;->desktopMode:Lcom/android/wm/shell/desktopmode/api/IDesktopMode;\n"
    assert s.count(old) == 1, 'unexpected launcher build: SystemUiProxy changed'
    open(p, 'w').write(s.replace(old, "    :goto_8\n    const/4 v0, 0x0\n\n    iput-object v0, p0, Lcom/android/quickstep/SystemUiProxy;->desktopMode:Lcom/android/wm/shell/desktopmode/api/IDesktopMode;\n"))
    print('patched', p)
