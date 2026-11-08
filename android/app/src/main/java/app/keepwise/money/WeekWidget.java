package app.keepwise.money;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;
import org.json.JSONArray;
import org.json.JSONObject;

// This week widget: seven days from today, each with what goes out (red) or comes in (green), as on Month in the app.
// The app sends the days (WidgetBridge.update "week"); nothing leaves the phone.
public class WeekWidget extends AppWidgetProvider {
    private static final int[] D = {R.id.kw_d0, R.id.kw_d1, R.id.kw_d2, R.id.kw_d3, R.id.kw_d4, R.id.kw_d5, R.id.kw_d6};
    private static final int[] N = {R.id.kw_n0, R.id.kw_n1, R.id.kw_n2, R.id.kw_n3, R.id.kw_n4, R.id.kw_n5, R.id.kw_n6};
    private static final int[] T = {R.id.kw_t0, R.id.kw_t1, R.id.kw_t2, R.id.kw_t3, R.id.kw_t4, R.id.kw_t5, R.id.kw_t6};
    private static final int[] A = {R.id.kw_a0, R.id.kw_a1, R.id.kw_a2, R.id.kw_a3, R.id.kw_a4, R.id.kw_a5, R.id.kw_a6};

    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) { for (int id : ids) m.updateAppWidget(id, views(c)); }

    static RemoteViews views(Context c) {
        SharedPreferences p = c.getSharedPreferences(KeepWiseWidget.PREFS, Context.MODE_PRIVATE);
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.keepwise_week);
        // what comes in and what goes out this week, each in its own pill, as in the app
        String in = p.getString("weekInSum", ""), out = p.getString("weekSum", "");
        v.setTextViewText(R.id.kw_win, in);
        v.setViewVisibility(R.id.kw_win, in.isEmpty() ? android.view.View.GONE : android.view.View.VISIBLE);
        boolean none = out.isEmpty() && in.isEmpty();
        v.setTextViewText(R.id.kw_wsum, none ? "Open KeepWise" : out);
        v.setViewVisibility(R.id.kw_wsum, !none && out.isEmpty() ? android.view.View.GONE : android.view.View.VISIBLE);
        try {
            JSONArray w = new JSONArray(p.getString("week", "[]"));
            for (int i = 0; i < 7; i++) {
                JSONObject d = i < w.length() ? w.getJSONObject(i) : new JSONObject();
                String k = d.optString("k", "");
                v.setTextViewText(N[i], d.optString("n", ""));
                v.setTextViewText(T[i], d.optString("t", ""));
                v.setTextViewText(A[i], d.optString("a", ""));
                v.setTextColor(A[i], "in".equals(k) ? 0xFF0B7A55 : 0xFFB3362F);
                v.setInt(D[i], "setBackgroundResource", i == 0 ? R.drawable.wk_today : "out".equals(k) ? R.drawable.wk_dayout : "in".equals(k) ? R.drawable.wk_dayin : R.drawable.wk_day);
            }
        } catch (Exception e) { /* leave the days blank until the app sends them */ }
        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.kw_wroot, PendingIntent.getActivity(c, 21, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        return v;
    }

    static void refresh(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, WeekWidget.class));
        for (int id : ids) m.updateAppWidget(id, views(c));
    }
}
