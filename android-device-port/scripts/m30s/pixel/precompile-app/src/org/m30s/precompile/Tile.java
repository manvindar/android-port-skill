package org.m30s.precompile;

import android.graphics.drawable.Icon;
import android.service.quicksettings.TileService;

/** Quick Settings tile: tap to compile the apps; lit while the job runs. */
public class Tile extends TileService {
    private void show(boolean on) {
        android.service.quicksettings.Tile t = getQsTile();
        if (t == null) return;
        t.setIcon(Icon.createWithResource(this, android.R.drawable.ic_popup_sync));
        t.setLabel("Precompile apps");
        t.setState(on ? android.service.quicksettings.Tile.STATE_ACTIVE : android.service.quicksettings.Tile.STATE_INACTIVE);
        t.updateTile();
    }

    @Override public void onStartListening() { show(Go.running()); }

    @Override public void onClick() { show(Go.start()); }
}
