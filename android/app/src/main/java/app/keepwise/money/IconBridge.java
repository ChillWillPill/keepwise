package app.keepwise.money;

import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

// The home screen icon follows the chosen theme. Switching the launcher entry while the app is on screen can close it
// on some phones, so the choice is remembered here and applied when the app goes to the background (MainActivity.onStop).
@CapacitorPlugin(name = "IconBridge")
public class IconBridge extends Plugin {
    static final String PREFS = "keepwise_icon";
    static final String[] THEMES = {"classic", "owl", "cream", "midnight", "ocean", "mocha", "rose", "contrast", "glass", "terminal"};

    @PluginMethod
    public void set(PluginCall call) {
        String t = call.getString("name", "classic");
        boolean known = false;
        for (String x : THEMES) if (x.equals(t)) known = true;
        if (!known) t = "classic";
        getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("want", t).apply();
        call.resolve();
    }

    static void apply(Context ctx) {
        SharedPreferences p = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String want = p.getString("want", null), now = p.getString("now", "classic");
        if (want == null || want.equals(now)) return;
        PackageManager pm = ctx.getPackageManager();
        try {
            // turn the new one on first, so there is never a moment with no icon
            pm.setComponentEnabledSetting(new ComponentName(ctx, "app.keepwise.money.Icon_" + want),
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP);
            for (String x : THEMES) if (!x.equals(want))
                pm.setComponentEnabledSetting(new ComponentName(ctx, "app.keepwise.money.Icon_" + x),
                    PackageManager.COMPONENT_ENABLED_STATE_DISABLED, PackageManager.DONT_KILL_APP);
            p.edit().putString("now", want).apply();
        } catch (Exception e) { /* keep whatever icon is showing */ }
    }
}
