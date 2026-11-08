package app.keepwise.money;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

// The app hands the home screen widget its few lines of text; they stay on this phone.
@CapacitorPlugin(name = "WidgetBridge")
public class WidgetBridge extends Plugin {
    static final String ACTION = "kw_widget_action";
    static String pending = null;   // what a widget tap asked for ("ask" or "voice"), until the app picks it up

    static void note(Intent i) { if (i != null && i.hasExtra(ACTION)) { pending = i.getStringExtra(ACTION); i.removeExtra(ACTION); } }

    @PluginMethod
    public void take(PluginCall call) {
        JSObject r = new JSObject();
        r.put("action", pending == null ? "" : pending);
        pending = null;
        call.resolve(r);
    }

    @PluginMethod
    public void update(PluginCall call) {
        SharedPreferences p = getContext().getSharedPreferences(KeepWiseWidget.PREFS, Context.MODE_PRIVATE);
        p.edit()
            .putString("label", call.getString("label", ""))
            .putString("amount", call.getString("amount", ""))
            .putString("next", call.getString("next", ""))
            .putString("week", call.getString("week", "[]"))
            .putString("weekSum", call.getString("weekSum", ""))
            .putString("weekInSum", call.getString("weekInSum", ""))
            .apply();
        KeepWiseWidget.refresh(getContext());
        WeekWidget.refresh(getContext());
        call.resolve();
    }
}
