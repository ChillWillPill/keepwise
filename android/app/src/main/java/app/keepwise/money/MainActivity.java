package app.keepwise.money;

import android.os.Bundle;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    // Phones set to very large text made words stack one letter per line. KeepWise still follows the phone's
    // text size, up to 130% of normal, which every screen is checked against; beyond that it stays at 130%.
    private static final int MAX_TEXT_ZOOM = 130;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(WidgetBridge.class);   // the home screen widget's link to the app
        registerPlugin(VoiceBridge.class);    // speaking to the owl
        super.onCreate(savedInstanceState);
        capTextZoom();
    }

    @Override
    public void onResume() {
        super.onResume();
        capTextZoom();   // the phone's text size can change while the app is in the background
    }

    private void capTextZoom() {
        if (getBridge() == null || getBridge().getWebView() == null) return;
        WebSettings s = getBridge().getWebView().getSettings();
        int scale = Math.round(getResources().getConfiguration().fontScale * 100);
        s.setTextZoom(Math.max(85, Math.min(MAX_TEXT_ZOOM, scale)));
    }
}
