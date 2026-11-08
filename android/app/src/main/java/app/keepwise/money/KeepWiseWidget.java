package app.keepwise.money;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

// Home screen widget: what you'll keep this month and what's due next. Tapping it opens KeepWise.
public class KeepWiseWidget extends AppWidgetProvider {
    static final String PREFS = "keepwise_widget";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) manager.updateAppWidget(id, views(context));
    }

    static RemoteViews views(Context c) {
        SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.keepwise_widget);
        String amount = p.getString("amount", "");
        v.setTextViewText(R.id.kw_label, nz(p.getString("label", ""), "What you'll keep"));
        v.setTextViewText(R.id.kw_amount, nz(amount, "Open KeepWise"));
        v.setTextViewText(R.id.kw_next, nz(p.getString("next", ""), amount.isEmpty() ? "Set up your month to see it here" : ""));
        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.kw_root, PendingIntent.getActivity(c, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        return v;
    }

    static void refresh(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, KeepWiseWidget.class));
        for (int id : ids) m.updateAppWidget(id, views(c));
    }

    private static String nz(String s, String fallback) { return s == null || s.isEmpty() ? fallback : s; }
}
