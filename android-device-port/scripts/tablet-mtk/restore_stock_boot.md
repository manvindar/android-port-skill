# Getting the tablet back when it will not reach TWRP or fastboot

`fastboot boot` is ignored by this bootloader, so every kernel test means writing `boot`. If the tablet is stuck (black screen, no USB):

1. Save the stock `boot` partition first (`adb shell dd if=/dev/block/by-name/boot ...` from TWRP) and check its hash.
2. Power off fully (hold Power ~15 s), unplug. Hold **Volume Up + Volume Down** and plug in USB. The Mac sees `Generic CDC` (MediaTek BROM).
3. `sudo mtk w boot stock-boot.img` with [mtkclient](https://github.com/bkerler/mtkclient). Run it as root (macOS blocks raw USB otherwise) and start it *before* you plug the cable in.
   The tool's `Kamakiri` exploit bypasses the protected BROM; a failed first try leaves the chip half-way, so power-cycle between attempts.
4. Unplug, hold Power to boot.

Only `boot` is written. `recovery` is never touched.
