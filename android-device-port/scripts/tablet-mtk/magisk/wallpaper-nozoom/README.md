# wallpaper-nozoom

Static overlay `config_wallpaperMaxScale = 1.0` (framework default 1.1). The Pixel Launcher calls `WallpaperManager.setWallpaperZoomOut` on every frame of the app drawer
animation; the window manager rescales the wallpaper layer, and because the vendor HWC cannot scale and rotate a layer, SurfaceFlinger redraws the wallpaper on the GPU each time.
With the overlay those per-frame redraws are gone (147 to 64 wallpaper `DrawLayer`s in a 12 s drawer test, the rest are region sampling screenshots), but the drawer
benchmark did not get better (29 to 39% janky frames against about 28% before), so it is **not** in the ROM image. It is kept as an optional module: the wallpaper no longer zooms out when the drawer opens.

Needs a reboot (`WindowManager` reads the value once). Check: `cmd overlay lookup --user 0 android android:dimen/config_wallpaperMaxScale` prints 1.0.
Remove: delete `/data/adb/modules/wallpaper-nozoom` and reboot.
