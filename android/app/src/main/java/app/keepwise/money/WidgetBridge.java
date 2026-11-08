package app.keepwise.money;

import android.content.Context;
import android.content.SharedPreferences;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

// The app hands the home screen widget its few lines of text; they stay on this phone.
@CapacitorPlugin(name = "WidgetBridge")
public class WidgetBridge extends Plugin {
    @PluginMethod
    public void update(PluginCall call) {
        SharedPreferences p = getContext().getSharedPreferences(KeepWiseWidget.PREFS, Context.MODE_PRIVATE);
        p.edit()
            .putString("label", call.getString("label", ""))
            .putString("amount", call.getString("amount", ""))
            .putString("next", call.getString("next", ""))
            .apply();
        KeepWiseWidget.refresh(getContext());
        call.resolve();
    }
}
