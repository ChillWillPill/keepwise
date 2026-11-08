package app.keepwise.money;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

// Quick add widget: tap the box to type (the owl opens with the keyboard up), the mic to speak, or the owl to open it.
public class QuickAddWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context c, AppWidgetManager manager, int[] ids) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.keepwise_quick);
        v.setOnClickPendingIntent(R.id.kq_root, open(c, "ask", 11));
        v.setOnClickPendingIntent(R.id.kq_field, open(c, "type", 13));
        v.setOnClickPendingIntent(R.id.kq_mic, open(c, "voice", 12));
        String said = c.getSharedPreferences(KeepWiseWidget.PREFS, Context.MODE_PRIVATE).getString("said", "");
        if (!said.isEmpty()) v.setTextViewText(R.id.kq_said, said);
        v.setOnClickPendingIntent(R.id.kq_said, open(c, "ask", 14));
        for (int id : ids) manager.updateAppWidget(id, v);
    }

    static void refresh(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        new QuickAddWidget().onUpdate(c, m, m.getAppWidgetIds(new android.content.ComponentName(c, QuickAddWidget.class)));
    }

    static PendingIntent open(Context c, String action, int code) {
        Intent i = new Intent(c, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        i.putExtra(WidgetBridge.ACTION, action);
        return PendingIntent.getActivity(c, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
