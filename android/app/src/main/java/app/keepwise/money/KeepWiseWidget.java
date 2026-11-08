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
        // the last three things spent
        int[] row = {R.id.kw_r0, R.id.kw_r1, R.id.kw_r2}, rn = {R.id.kw_rn0, R.id.kw_rn1, R.id.kw_rn2}, rw = {R.id.kw_rw0, R.id.kw_rw1, R.id.kw_rw2}, ra = {R.id.kw_ra0, R.id.kw_ra1, R.id.kw_ra2};
        int shown = 0;
        try {
            org.json.JSONArray r = new org.json.JSONArray(p.getString("recent", "[]"));
            for (int i = 0; i < 3; i++) {
                boolean has = i < r.length();
                v.setViewVisibility(row[i], has ? android.view.View.VISIBLE : android.view.View.GONE);
                if (!has) continue;
                org.json.JSONObject x = r.getJSONObject(i);
                v.setTextViewText(rn[i], x.optString("n", ""));
                v.setTextViewText(rw[i], x.optString("w", ""));
                v.setTextViewText(ra[i], x.optString("a", ""));
                shown++;
            }
        } catch (Exception e) { shown = 0; }
        v.setViewVisibility(R.id.kw_recent, shown > 0 ? android.view.View.VISIBLE : android.view.View.GONE);
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
