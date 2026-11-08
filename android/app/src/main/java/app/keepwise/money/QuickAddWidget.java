package app.keepwise.money;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

// Quick add widget: tap the owl to open KeepWise ready to log or ask; tap the microphone to start speaking straight away.
public class QuickAddWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context c, AppWidgetManager manager, int[] ids) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.keepwise_quick);
        v.setOnClickPendingIntent(R.id.kq_root, open(c, "ask", 11));
        v.setOnClickPendingIntent(R.id.kq_mic, open(c, "voice", 12));
        for (int id : ids) manager.updateAppWidget(id, v);
    }

    static PendingIntent open(Context c, String action, int code) {
        Intent i = new Intent(c, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        i.putExtra(WidgetBridge.ACTION, action);
        return PendingIntent.getActivity(c, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
