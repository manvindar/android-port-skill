#!/usr/bin/env python3
"""Pixel Launcher all-apps search NPEs when the system has no SearchUiManager (GSI without a search UI service): return early instead.
usage: patch_search_session.py APKTOOL_DECODED_DIR"""
import glob, sys
for p in glob.glob(sys.argv[1] + '/smali*/com/google/android/apps/nexuslauncher/allapps/y4.smali'):
    s = open(p).read()
    old = "    :cond_b\n    const/16 v3, 0xc8\n\n    invoke-direct {v2, v4, v3, v0}, Landroid/app/search/SearchContext;-><init>(IILandroid/os/Bundle;)V\n"
    assert s.count(old) == 1, 'unexpected launcher build: class y4 changed'
    open(p, 'w').write(s.replace(old, "    :cond_b\n    if-nez v1, :px_have_search\n\n    return-void\n\n    :px_have_search\n" + old.split(':cond_b\n')[1]))
    print('patched', p)
