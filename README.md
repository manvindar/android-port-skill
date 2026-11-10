# android-port-skill

One Claude Code skill, `android-device-port`, with the notes, scripts and patches from two device ports:

- Samsung Galaxy M30s (Exynos 9611, kernel 4.14, Android 11 vendor): Android 17 GSI + Pixel 9a layer (track A) and Samsung One UI 9 from a donor firmware (track B).
- Lenovo Tab M10 FHD Plus TB-X606V (MT8768, kernel 4.9, Android 10 vendor): Android 14/16/17 GSIs + Pixel Tablet layer.

It lets an agent port a newer Android onto an older Treble device: recon, track choice, size budget, image pipeline, kernel gaps, every fix we needed (symptom -> cause -> fix -> script), flashing with hash verification and selective wipe, CI, tests and hard rules.

## Install as a Claude Code plugin

Run these two commands in your terminal:

```sh
claude plugin marketplace add manvindar/android-port-skill
claude plugin install android-port@manvindar-android
```

Start a new Claude Code session, then invoke `/android-port:android-device-port` or ask for help with an Android port. The plugin includes the skill, references and source tools; it does not run scripts or flash a phone during installation.

Inside Claude Code you can also use `/plugin marketplace add manvindar/android-port-skill`, then `/plugin install android-port@manvindar-android` and confirm Install in the plugin panel.

To update:

```sh
claude plugin marketplace update manvindar-android
claude plugin update android-port@manvindar-android
```

### Manual skill installation

Clone this repository, then copy `android-device-port/` into `~/.claude/skills/` for Claude Code, or `~/.agents/skills/` for Codex. Keep the whole folder so references and scripts stay available.

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
