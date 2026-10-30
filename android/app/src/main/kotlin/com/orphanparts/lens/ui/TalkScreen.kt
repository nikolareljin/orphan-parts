package com.orphanparts.lens.ui

import android.Manifest
import android.content.pm.PackageManager
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.orphanparts.lens.api.ItemLine
import com.orphanparts.lens.audio.WavRecorder
import kotlinx.coroutines.launch
import java.util.Locale

/** Hold to talk: what you say about an item is transcribed by the backend, kept on the item as
 * your words, and read back so you hear what was kept. */
@Composable
fun TalkScreen(session: Session, lastItemId: Int?) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val recorder = remember { WavRecorder() }
    var items by remember { mutableStateOf<List<ItemLine>>(emptyList()) }
    var itemId by remember(lastItemId) { mutableStateOf(lastItemId) }
    var allowed by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    var status by remember { mutableStateOf("") }
    var transcript by remember { mutableStateOf("") }
    var holding by remember { mutableStateOf(false) }
    var speaker by remember { mutableStateOf<TextToSpeech?>(null) }

    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }

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
        Spacer(Modifier.height(8.dp))
        Text(
            "Hold the button and talk: what it is, what is wrong with it, what you tested. The backend writes it down as your words and the phone reads it back.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(12.dp))
        val current = items.firstOrNull { it.id == itemId }
        Text(
            when {
                current != null -> "Item #${current.id}: ${current.name} (${current.itemType})"
                itemId != null -> "Item #$itemId"
                else -> "No item yet: capture one first."
            },
            style = MaterialTheme.typography.titleMedium,
        )
        if (items.size > 1) {
            OutlinedButton(onClick = {
                val index = items.indexOfFirst { it.id == itemId }
                itemId = items[(index + 1).mod(items.size)].id
            }) { Text("Next item") }
        }
        Spacer(Modifier.height(16.dp))
        if (!allowed) {
            Button(onClick = { askPermission.launch(Manifest.permission.RECORD_AUDIO) }) { Text("Allow the microphone") }
        } else {
            val colors = MaterialTheme.colorScheme
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(72.dp)
                    .background(if (holding) colors.secondary else colors.primary, MaterialTheme.shapes.large)
                    .semantics { role = Role.Button }
                    .pointerInput(itemId) {
                    detectTapGestures(
                        onPress = {
                            val id = itemId ?: return@detectTapGestures
                            holding = true
                            status = "Listening…"
                            recorder.start()
                            tryAwaitRelease()
                            holding = false
                            val wav = recorder.stop()
                            if (wav == null) {
                                status = recorder.problem?.let { "Nothing heard: $it." } ?: "Nothing heard."
                            } else {
                                status = "Writing it down (${"%.1f".format(recorder.seconds())} s)…"
                                scope.launch {
                                    try {
                                        val note = session.call { it.voiceNote(id, wav) }
                                        transcript = note.transcript
                                        status = (if (note.cut) "Kept, cut at the limit. " else "Kept as your words. ") + "Heard by ${note.model}."
                                        speaker?.speak(note.transcript, TextToSpeech.QUEUE_FLUSH, null, "note")
                                    } catch (e: Exception) {
                                        status = "Could not keep it: ${describe(e)}"
                                    }
                                }
                            }
                        },
                    )
                },
            ) { Text(if (holding) "Listening… release when done" else "Hold to talk", color = colors.onPrimary) }
        }
        Spacer(Modifier.height(12.dp))
        Text(status, style = MaterialTheme.typography.bodyMedium)
        if (transcript.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text("“$transcript”", style = MaterialTheme.typography.bodyLarge)
        }
    }
}
