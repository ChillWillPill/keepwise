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
        // the ring: what share of this month's money you keep
        int pct = p.getInt("pct", -1);
        v.setViewVisibility(R.id.kw_side, pct < 0 ? android.view.View.GONE : android.view.View.VISIBLE);
        if (pct >= 0) {
            v.setImageViewBitmap(R.id.kw_ring, ring(c, pct, p.getBoolean("hide", false), p.getString("parts", "[]")));
            v.setTextViewText(R.id.kw_safe, p.getString("safe", ""));
        }
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

    static android.graphics.Bitmap ring(Context c, int pct, boolean hide, String parts) {
        float d = c.getResources().getDisplayMetrics().density;
        int s = Math.round(76 * d); float w = 9 * d, r = s / 2f - w / 2f;
        android.graphics.Bitmap b = android.graphics.Bitmap.createBitmap(s, s, android.graphics.Bitmap.Config.ARGB_8888);
        android.graphics.Canvas k = new android.graphics.Canvas(b);
        android.graphics.Paint pa = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        pa.setStyle(android.graphics.Paint.Style.STROKE); pa.setStrokeWidth(w); pa.setStrokeCap(android.graphics.Paint.Cap.ROUND);
        android.graphics.RectF o = new android.graphics.RectF(s / 2f - r, s / 2f - r, s / 2f + r, s / 2f + r);
        pa.setColor(0x33FFFFFF); k.drawArc(o, 0, 360, false, pa);
        // where the month goes, slice by slice like the chart in the app (what you keep in white)
        pa.setStrokeCap(android.graphics.Paint.Cap.BUTT);
        float at = -90;
        try {
            org.json.JSONArray a = new org.json.JSONArray(parts);
            for (int i = 0; i < a.length(); i++) {
                org.json.JSONObject x = a.getJSONObject(i);
                float sweep = 360f * (float) x.optDouble("p", 0) / 100f;
                if (sweep <= 0) continue;
                pa.setColor(android.graphics.Color.parseColor(x.optString("c", "#FFFFFF")));
                k.drawArc(o, at + 1.5f, Math.max(0.5f, sweep - 3f), false, pa);   // a hairline gap between slices
                at += sweep;
            }
        } catch (Exception e) { pa.setColor(0xFFFFD25E); if (pct > 0) k.drawArc(o, -90, 360f * Math.min(100, pct) / 100f, false, pa); }
        android.graphics.Paint t = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
        t.setColor(0xFFFFFFFF); t.setTextAlign(android.graphics.Paint.Align.CENTER); t.setFakeBoldText(true); t.setTextSize(18 * d);
        k.drawText(hide ? "••" : pct + "%", s / 2f, s / 2f + 2 * d, t);
        t.setFakeBoldText(false); t.setTextSize(10 * d); t.setColor(0xFFD9F5E9);
        k.drawText("kept", s / 2f, s / 2f + 15 * d, t);
        return b;
    }

    static void refresh(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, KeepWiseWidget.class));
        for (int id : ids) m.updateAppWidget(id, views(c));
    }

    private static String nz(String s, String fallback) { return s == null || s.isEmpty() ? fallback : s; }
}
