# android-port-skill

One Claude Code skill, `android-device-port`, with the notes, scripts and patches from two device ports:

- Samsung Galaxy M30s (Exynos 9611, kernel 4.14, Android 11 vendor): Android 17 GSI + Pixel 9a layer (track A) and Samsung One UI 9 from a donor firmware (track B).
- Lenovo Tab M10 FHD Plus TB-X606V (MT8768, kernel 4.9, Android 10 vendor): Android 14/16/17 GSIs + Pixel Tablet layer.

It lets an agent port a newer Android onto an older Treble device: recon, track choice, size budget, image pipeline, kernel gaps, every fix we needed (symptom -> cause -> fix -> script), flashing with hash verification and selective wipe, CI, tests and hard rules.

## Install

```
mkdir -p ~/.claude/skills && cp -R android-device-port ~/.claude/skills/
```
or symlink the directory. Claude Code loads `SKILL.md` and reads `references/` on demand.

## Layout

```
android-device-port/
  SKILL.md                 decision tree and map (under 500 lines)
  references/              recon, flashing, boot diagnosis, track A, track B, kernel, system patches,
                           HAL shims, M30s quirks, Lenovo/MTK, CI, testing, pitfalls, patch index
  scripts/                 m30s/ (image builders, oneui/, fphal/, pixel/, debug/, probe/, backup/),
                           tablet-mtk/ (patch library), ci/ (workflows), kernel-build/
  patches/                 kernel-4.14/ (PSI series, HDR, touch boost), kernel-4.9-mtk/, kernel-config/
```

## What is not here

No firmware, vendor blobs, donor files, keys, device identifiers or personal data. Rebuild the inputs from your own downloads. Respect the owner-selected source and release visibility. Device logs, credentials and private history are excluded.
