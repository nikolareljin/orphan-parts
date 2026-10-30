package com.orphanparts.lens.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.orphanparts.lens.api.Capture
import com.orphanparts.lens.audio.WavRecorder
import com.orphanparts.lens.preparePhoto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

const val MAX_PHOTOS = 4
const val CLIP_SECONDS = 30

/** The largest clip the backend takes (MAX_CLIP_MB), less a margin for the container's own bytes. */
const val CLIP_MAX_BYTES = 56L * 1024 * 1024

/** The system camera, recording a clip of at most CLIP_SECONDS and CLIP_MAX_BYTES into the file
 * given: the camera stops at whichever comes first, so a high-quality clip is not refused later. */
class ShortClip : ActivityResultContracts.CaptureVideo() {
    override fun createIntent(context: Context, input: Uri): Intent =
        super.createIntent(context, input)
            .putExtra(MediaStore.EXTRA_DURATION_LIMIT, CLIP_SECONDS)
            .putExtra(MediaStore.EXTRA_SIZE_LIMIT, CLIP_MAX_BYTES)
}

/** One capture: photos, a clip, a spoken note and a line, sent together. The backend keeps
 * the bundle and reads it into an item when asked; the photos are re-encoded here first. */
@Composable
fun CaptureScreen(session: Session, onSent: (Capture) -> Unit) {
    val context = LocalContext.current
    // a scope of the screen's own, not of its composition: a send in flight lands, and is said,
    // even when the person switches tabs before the answer (a second send would duplicate it)
    val scope = remember { CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate) }
    val recorder = remember { WavRecorder() }
    var photos by remember { mutableStateOf<List<Pair<ByteArray, Bitmap>>>(emptyList()) }
    var clip by remember { mutableStateOf<ByteArray?>(null) }
    var audio by remember { mutableStateOf<ByteArray?>(null) }
    var audioSeconds by remember { mutableStateOf(0.0) }
    // the typed line and name survive a process death behind the camera app; the bytes do not
    var name by rememberSaveable { mutableStateOf("") }
    var note by rememberSaveable { mutableStateOf("") }
    var holding by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    // kept across a process death while the camera app is in front, so the result still lands
    var pendingUri by rememberSaveable { mutableStateOf<String?>(null) }
    var allowed by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }

    fun fileUri(name: String): Uri {
        val dir = File(context.cacheDir, "captures").apply { mkdirs() }
        return FileProvider.getUriForFile(context, context.packageName + ".files", File(dir, name))
    }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = pendingUri?.let(Uri::parse)
        if (!ok || uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            // a photo the phone cannot open or decode (gone, refused, too large for memory) is
            // said on the screen, never a crash
            val prepared = withContext(Dispatchers.IO) {
                try {
                    preparePhoto(context.contentResolver.openInputStream(uri)?.use { it.readBytes() })
                } catch (e: Exception) {
                    null
                } catch (e: OutOfMemoryError) {
                    null
                }
            }
            if (prepared == null) {
                status = "The photo could not be read."
            } else {
                photos = photos + prepared
                status = "Photo ${photos.size} ready (${prepared.first.size / 1024} KB)."
            }
        }
    }
    val takeClip = rememberLauncherForActivityResult(ShortClip()) { ok ->
        val uri = pendingUri?.let(Uri::parse)
        if (!ok || uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val bytes = withContext(Dispatchers.IO) { context.contentResolver.openInputStream(uri)?.use { it.readBytes() } }
            if (bytes != null && bytes.isEmpty()) {
                // a camera app that said yes but wrote nothing (some ignore the output file)
                clip = null
                status = "The camera returned an empty clip; record it again."
            } else if (bytes != null && bytes.size > CLIP_MAX_BYTES) {
                clip = null
                status = "The clip is ${bytes.size / 1024 / 1024} MB, more than the backend takes; record a shorter one."
            } else {
                clip = bytes
                status = if (bytes == null) "The clip could not be read." else "Clip ready (${bytes.size / 1024} KB)."
            }
        }
    }

    fun clear() {
        photos = emptyList()
        clip = null
        audio = null
        audioSeconds = 0.0
        name = ""
        note = ""
    }

    Column(Modifier.verticalScroll(rememberScrollState())) {
        Text("Capture a thing", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        Text(
            "Photos of the item and its label (tap the label in the camera to focus on it, fill the frame), a short clip if it moves or makes a sound, and what you know about it, said or typed. Send it, and the backend reads it into your inventory.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(12.dp))
        Row {
            Button(
                enabled = photos.size < MAX_PHOTOS && !busy,
                onClick = {
                    val uri = fileUri("photo-${System.currentTimeMillis()}.jpg")
                    pendingUri = uri.toString()
                    takePicture.launch(uri)
                },
            ) { Text(if (photos.isEmpty()) "Take a photo" else "Another photo (${photos.size}/$MAX_PHOTOS)") }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(
                enabled = !busy,
                onClick = {
                    val uri = fileUri("clip-${System.currentTimeMillis()}.mp4")
                    pendingUri = uri.toString()
                    takeClip.launch(uri)
                },
            ) { Text(if (clip == null) "Record a clip" else "Clip again") }
        }
        if (photos.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Row {
                for ((n, photo) in photos.withIndex()) {
                    Image(
                        photo.second.asImageBitmap(),
                        contentDescription = "Photo ${n + 1}",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.size(72.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        if (!allowed) {
            OutlinedButton(onClick = { askPermission.launch(Manifest.permission.RECORD_AUDIO) }) { Text("Allow the microphone") }
        } else {
            val colors = MaterialTheme.colorScheme
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(64.dp)
                    .background(if (holding) colors.secondary else colors.primary, MaterialTheme.shapes.large)
                    .semantics { role = Role.Button }
                    .pointerInput(Unit) {
                        detectTapGestures(
                            onPress = {
                                holding = true
                                recorder.start()
                                tryAwaitRelease()
                                holding = false
                                val wav = recorder.stop()
                                audio = wav
                                audioSeconds = if (wav == null) 0.0 else recorder.seconds()
                                status = if (wav == null) "Nothing heard." else "Note ready (${"%.1f".format(audioSeconds)} s)."
                            },
                        )
                    },
            ) {
                Text(
                    when {
                        holding -> "Listening… release when done"
                        audio != null -> "Hold to talk again (${"%.1f".format(audioSeconds)} s kept)"
                        else -> "Hold to talk: what is it, what is wrong, what you tested"
                    },
                    color = colors.onPrimary,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name, if you know it") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("A line about it") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(12.dp))
        Row {
            Button(
                enabled = !busy && (photos.isNotEmpty() || clip != null || audio != null || note.isNotBlank()),
                onClick = {
                    busy = true
                    status = "Sending…"
                    val bundle = photos.map { it.first }
                    val sentClip = clip
                    val sentAudio = audio
                    scope.launch {
                        try {
                            val kept = session.call { it.sendCapture(bundle, sentClip, sentAudio, name.trim(), note.trim()) }
                            status = "Sent as capture #${kept.id}: ${kept.photos} photo(s)${if (kept.clip) ", a clip" else ""}${if (kept.audio) ", a note" else ""}. See Captures."
                            clear()
                            onSent(kept)
                        } catch (e: Exception) {
                            status = "Could not send: ${describe(e)}"
                        } finally {
                            busy = false
                        }
                    }
                },
            ) { Text(if (busy) "Sending…" else "Send") }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(enabled = !busy, onClick = { clear(); status = "" }) { Text("Clear") }
        }
        Spacer(Modifier.height(8.dp))
        Text(status, style = MaterialTheme.typography.bodyMedium)
    }
}
