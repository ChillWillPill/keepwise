package app.keepwise.money;

import android.Manifest;
import android.content.Intent;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.util.ArrayList;

// Speaking to the owl inside the app. The app's web view has no speech-to-text of its own, so this uses the phone's
// speech service and passes the words back as they are heard. Nothing is recorded or kept by KeepWise.
@CapacitorPlugin(name = "VoiceBridge", permissions = { @Permission(strings = { Manifest.permission.RECORD_AUDIO }, alias = "mic") })
public class VoiceBridge extends Plugin {
    private SpeechRecognizer rec;

    @PluginMethod
    public void available(PluginCall call) {
        JSObject r = new JSObject();
        r.put("ok", SpeechRecognizer.isRecognitionAvailable(getContext()));
        call.resolve(r);
    }

    @PluginMethod
    public void start(PluginCall call) {
        if (getPermissionState("mic") != PermissionState.GRANTED) { requestPermissionForAlias("mic", call, "micDone"); return; }
        begin(call);
    }

    @PermissionCallback
    private void micDone(PluginCall call) {
        if (getPermissionState("mic") == PermissionState.GRANTED) begin(call); else call.reject("not-allowed");
    }

    private void begin(PluginCall call) {
        if (!SpeechRecognizer.isRecognitionAvailable(getContext())) { call.reject("service-not-allowed"); return; }
        final String lang = call.getString("lang", "en-US");
        getActivity().runOnUiThread(() -> {
            try {
                close();
                rec = SpeechRecognizer.createSpeechRecognizer(getContext());
                rec.setRecognitionListener(new RecognitionListener() {
                    public void onReadyForSpeech(Bundle b) {}
                    public void onBeginningOfSpeech() {}
                    public void onRmsChanged(float v) {}
                    public void onBufferReceived(byte[] b) {}
                    public void onEndOfSpeech() {}
                    public void onEvent(int t, Bundle b) {}
                    public void onPartialResults(Bundle b) { send(b, false); }
                    public void onResults(Bundle b) { send(b, true); finish(); }
                    public void onError(int code) {
                        JSObject e = new JSObject();
                        e.put("error", code == SpeechRecognizer.ERROR_NO_MATCH || code == SpeechRecognizer.ERROR_SPEECH_TIMEOUT ? "no-speech"
                            : code == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ? "not-allowed" : "network");
                        notifyListeners("voiceError", e);
                        finish();
                    }
                });
                Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
                i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang);
                i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
                i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 4000L);
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 4000L);
                rec.startListening(i);
                call.resolve();
            } catch (Exception ex) { call.reject("network"); }
        });
    }

    private void send(Bundle b, boolean fin) {
        ArrayList<String> m = b == null ? null : b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        JSObject r = new JSObject();
        r.put("text", m == null || m.isEmpty() ? "" : m.get(0));
        r.put("final", fin);
        notifyListeners("voiceResult", r);
    }

    private void finish() { close(); notifyListeners("voiceEnd", new JSObject()); }

    private void close() { if (rec != null) { try { rec.destroy(); } catch (Exception e) {} rec = null; } }

    @PluginMethod
    public void stop(PluginCall call) {
        getActivity().runOnUiThread(() -> { if (rec != null) { try { rec.stopListening(); } catch (Exception e) {} } });
        call.resolve();
    }

    @Override
    protected void handleOnDestroy() { close(); }
}
