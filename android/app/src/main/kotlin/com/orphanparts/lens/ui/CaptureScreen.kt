package com.orphanparts.lens.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.orphanparts.lens.api.Capture
import com.orphanparts.lens.audio.WavRecorder
import com.orphanparts.lens.looksLikeVideo
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
    // a hold that ends with the screen releases the microphone
    DisposableEffect(recorder) {
        onDispose { recorder.stop() }
    }
    var photos by remember { mutableStateOf<List<Pair<ByteArray, Bitmap>>>(emptyList()) }
    var clip by remember { mutableStateOf<ByteArray?>(null) }
    var audio by remember { mutableStateOf<ByteArray?>(null) }
    var audioSeconds by remember { mutableStateOf(0.0) }
    // the typed line and name survive a process death behind the camera app; the bytes do not
    var name by rememberSaveable { mutableStateOf("") }
    var note by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    // kept across a process death while the camera app is in front, so the result still lands
    var pendingUri by rememberSaveable { mutableStateOf<String?>(null) }
    var allowed by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }
    val colors = MaterialTheme.colorScheme

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
    // from the gallery: photos re-encoded as the camera's are, a clip checked by its bytes
    val pickPhotos = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(MAX_PHOTOS)) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        scope.launch {
            val room = MAX_PHOTOS - photos.size
            val prepared = withContext(Dispatchers.IO) {
                uris.take(room).mapNotNull { uri ->
                    try {
                        preparePhoto(context.contentResolver.openInputStream(uri)?.use { it.readBytes() })
                    } catch (e: Exception) {
                        null
                    } catch (e: OutOfMemoryError) {
                        null
                    }
                }
            }
            photos = photos + prepared
            status = when {
                prepared.isEmpty() -> "The photo could not be read."
                uris.size > room -> "${prepared.size} photo(s) added; an item keeps $MAX_PHOTOS."
                else -> "${prepared.size} photo(s) ready."
            }
        }
    }
    val pickClip = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val bytes = withContext(Dispatchers.IO) {
                try {
                    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } catch (e: Exception) {
                    null
                } catch (e: OutOfMemoryError) {
                    null
                }
            }
            when {
                bytes == null || bytes.isEmpty() -> { clip = null; status = "The clip could not be read." }
                bytes.size > CLIP_MAX_BYTES -> { clip = null; status = "The clip is ${bytes.size / 1024 / 1024} MB, more than the backend takes; pick a shorter one." }
                !looksLikeVideo(bytes) -> { clip = null; status = "The clip is not an MP4 or 3GP file; the backend takes those two." }
                else -> { clip = bytes; status = "Clip ready (${bytes.size / 1024} KB)." }
            }
        }
    }
    val takeClip = rememberLauncherForActivityResult(ShortClip()) { ok ->
        val uri = pendingUri?.let(Uri::parse)
        if (!ok || uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            // a clip the camera never wrote, or one too large for the phone's memory, is said,
            // never a crash
            val bytes = withContext(Dispatchers.IO) {
                try {
                    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } catch (e: Exception) {
                    null
                } catch (e: OutOfMemoryError) {
                    null
                }
            }
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

    Column {
        Text("Capture a thing", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(6.dp))
        Text(
            "Photos of the item and its label (tap the label in the camera to focus on it, fill the frame), a short clip if it moves or makes a sound, and what you know about it, said or typed. Send it, and the backend reads it into your inventory." +
                if (session.hasDoor) "" else " No code is set: a gated backend answers this phone as the demo visitor and keeps no capture; type the code or pair on the Backend tab.",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.onSurfaceVariant,
        )
        Spacer(Modifier.height(12.dp))
        Panel {
            Text("Show it", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(10.dp))
            Row {
                PrimaryButton(
                    if (photos.isEmpty()) "Take a photo" else "Another photo (${photos.size}/$MAX_PHOTOS)",
                    enabled = photos.size < MAX_PHOTOS && !busy,
                ) {
                    val uri = fileUri("photo-${System.currentTimeMillis()}.jpg")
                    pendingUri = uri.toString()
                    takePicture.launch(uri)
                }
                Spacer(Modifier.width(8.dp))
                SecondaryButton(if (clip == null) "Record a clip" else "Clip again", enabled = !busy) {
                    val uri = fileUri("clip-${System.currentTimeMillis()}.mp4")
                    pendingUri = uri.toString()
                    takeClip.launch(uri)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row {
                SecondaryButton("Photos from the gallery", enabled = photos.size < MAX_PHOTOS && !busy) {
                    pickPhotos.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }
                Spacer(Modifier.width(8.dp))
                SecondaryButton("A video from the gallery", enabled = !busy) {
                    pickClip.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.VideoOnly))
                }
            }
            if (photos.isNotEmpty() || clip != null) {
                Spacer(Modifier.height(10.dp))
                Row {
                    for ((n, photo) in photos.withIndex()) {
                        Image(
                            photo.second.asImageBitmap(),
                            contentDescription = "Photo ${n + 1}",
                            contentScale = ContentScale.Crop,
                            modifier = Modifier
                                .size(72.dp)
                                .clip(MaterialTheme.shapes.small)
                                .border(1.dp, colors.outline, MaterialTheme.shapes.small),
                        )
                        Spacer(Modifier.width(6.dp))
                    }
                    if (clip != null) Pill("a clip", Tone.Accent)
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Panel {
            Text("Say what you know", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(10.dp))
            if (!allowed) {
                SecondaryButton("Allow the microphone") { askPermission.launch(Manifest.permission.RECORD_AUDIO) }
            } else {
                HoldButton(
                    idle = if (audio != null) "Hold to talk again (${"%.1f".format(audioSeconds)} s kept)" else "Hold to talk: what is it, what is wrong, what you tested",
                    active = "Listening… release when done",
                    onStart = {
                        recorder.start()
                        true
                    },
                    onStop = {
                        val wav = recorder.stop()
                        audio = wav
                        audioSeconds = if (wav == null) 0.0 else recorder.seconds()
                        status = if (wav == null) "Nothing heard." else "Note ready (${"%.1f".format(audioSeconds)} s)."
                    },
                )
            }
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Name, if you know it") },
                singleLine = true,
                colors = fieldColors(),
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                label = { Text("A line about it") },
                colors = fieldColors(),
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Spacer(Modifier.height(12.dp))
        Row {
            PrimaryButton(
                if (busy) "Sending…" else "Send",
                enabled = !busy && (photos.isNotEmpty() || clip != null || audio != null || note.isNotBlank()),
            ) {
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
            }
            Spacer(Modifier.width(8.dp))
            SecondaryButton("Clear", enabled = !busy) {
                clear()
                status = ""
            }
        }
        Spacer(Modifier.height(8.dp))
        StatusLine(status)
    }
}
