package com.orphanparts.lens.ui

import android.Manifest
import android.content.pm.PackageManager
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.orphanparts.lens.api.ItemLine
import com.orphanparts.lens.audio.WavRecorder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.Locale

/** Hold to talk: what you say about an item is transcribed by the backend, kept on the item as
 * your words, and read back so you hear what was kept. */
@Composable
fun TalkScreen(session: Session, lastItemId: Int?) {
    val context = LocalContext.current
    // a scope of the screen's own, not of its composition: a note in flight is kept and said
    // on the item even when the person switches tabs before the answer
    val scope = remember { CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate) }
    val recorder = remember { WavRecorder() }
    var items by remember { mutableStateOf<List<ItemLine>>(emptyList()) }
    var itemId by remember(lastItemId) { mutableStateOf(lastItemId) }
    var allowed by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    var status by remember { mutableStateOf("") }
    var transcript by remember { mutableStateOf("") }
    var speaker by remember { mutableStateOf<TextToSpeech?>(null) }
    val muted = MaterialTheme.colorScheme.onSurfaceVariant

    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        allowed = granted
        if (!granted) status = "The microphone was refused. Allow it for this app in the phone's settings, then come back."
    }

    // a hold that ends with the screen (a tab switch mid-sentence) releases the microphone
    DisposableEffect(recorder) {
        onDispose { recorder.stop() }
    }

    DisposableEffect(Unit) {
        var tts: TextToSpeech? = null
        tts = TextToSpeech(context) { ok ->
            if (ok == TextToSpeech.SUCCESS) {
                tts?.language = Locale.getDefault()
                speaker = tts
            }
        }
        onDispose {
            tts?.shutdown()
            speaker = null
        }
    }

    LaunchedEffect(Unit) {
        try {
            items = session.call { it.items() }
            if (itemId == null) itemId = items.firstOrNull()?.id
        } catch (e: Exception) {
            status = "Could not list the items: ${describe(e)}"
        }
    }

    Column {
        Text("Say it about an item", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(6.dp))
        Text(
            "Hold the button and talk: what it is, what is wrong with it, what you tested. It is saved on the item as your words and read back to you.",
            style = MaterialTheme.typography.bodyMedium,
            color = muted,
        )
        Spacer(Modifier.height(12.dp))
        Panel {
            val current = items.firstOrNull { it.id == itemId }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    when {
                        current != null -> "Item #${current.id}: ${current.name}"
                        itemId != null -> "Item #$itemId"
                        else -> "No item yet: capture one first."
                    },
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                )
                if (current != null) {
                    Spacer(Modifier.width(8.dp))
                    Pill(current.itemType.replace('_', ' '))
                }
            }
            if (items.size > 1) {
                Spacer(Modifier.height(8.dp))
                SecondaryButton("Next item") {
                    val index = items.indexOfFirst { it.id == itemId }
                    itemId = items[(index + 1).mod(items.size)].id
                }
            }
            Spacer(Modifier.height(14.dp))
            if (!allowed) {
                PrimaryButton("Allow the microphone") { askPermission.launch(Manifest.permission.RECORD_AUDIO) }
            } else {
                HoldButton(
                    idle = "Hold to talk",
                    active = "Listening… release when done",
                    key = itemId,
                    onStart = {
                        if (itemId == null) {
                            false
                        } else {
                            status = "Listening…"
                            recorder.start()
                            true
                        }
                    },
                    onStop = {
                        val id = itemId
                        val wav = recorder.stop()
                        if (wav == null || id == null) {
                            status = recorder.problem?.let { "Nothing heard: $it." } ?: "Nothing heard."
                        } else {
                            status = "Writing it down (${"%.1f".format(recorder.seconds())} s)…"
                            scope.launch {
                                try {
                                    val note = session.call { it.voiceNote(id, wav) }
                                    transcript = note.transcript
                                    status = (if (note.cut) "Saved, cut at the length limit. " else "Saved as your words. ") + "Heard by ${note.model}."
                                    speaker?.speak(note.transcript, TextToSpeech.QUEUE_FLUSH, null, "note")
                                } catch (e: Exception) {
                                    status = "Could not keep it: ${describe(e)}"
                                }
                            }
                        }
                    },
                )
            }
            Spacer(Modifier.height(10.dp))
            StatusLine(status)
            if (transcript.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Text("“$transcript”", style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}
