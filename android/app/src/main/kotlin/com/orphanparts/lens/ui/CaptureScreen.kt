package com.orphanparts.lens.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import com.orphanparts.lens.api.Extraction
import com.orphanparts.lens.api.SavedItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

private const val MAX_SIDE = 1600

/** A photo of the label through the system camera, read by the backend, saved privately. The
 * photo is re-encoded here, so no metadata leaves the phone. */
@Composable
fun CaptureScreen(session: Session, onSaved: (SavedItem) -> Unit) {
    val context = LocalContext.current
    // a scope of the screen's own, not of its composition: a save in flight lands, and is said,
    // even when the person switches tabs before the answer (a second save would duplicate it)
    val scope = remember { CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate) }
    // kept across a process death while the camera app is in front, so the result still lands
    var photoUri by rememberSaveable { mutableStateOf<String?>(null) }
    var jpeg by remember { mutableStateOf<ByteArray?>(null) }
    var preview by remember { mutableStateOf<Bitmap?>(null) }
    var extraction by remember { mutableStateOf<Extraction?>(null) }
    var name by remember { mutableStateOf("") }
    var condition by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var saved by remember { mutableStateOf<SavedItem?>(null) }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = photoUri?.let(Uri::parse)
        if (!ok || uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            // a photo the phone cannot open or decode (gone, refused, too large for memory) is
            // said on the screen, never a crash
            val prepared = withContext(Dispatchers.IO) {
                try {
                    prepare(context.contentResolver.openInputStream(uri)?.use { it.readBytes() })
                } catch (e: Exception) {
                    null
                } catch (e: OutOfMemoryError) {
                    null
                }
            }
            jpeg = prepared?.first
            preview = prepared?.second
            extraction = null
            saved = null
            status = if (prepared == null) "The photo could not be read." else "Photo ready: ${prepared.first.size / 1024} KB."
        }
    }

    Column(Modifier.verticalScroll(rememberScrollState())) {
        Text("Read a label", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        Text(
            "Fill the frame with the label, straight on, in good light. For a feature to measure later, put a ruler in the same plane and mark it on the web.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(12.dp))
        Row {
            Button(onClick = {
                val dir = File(context.cacheDir, "captures").apply { mkdirs() }
                val file = File(dir, "capture.jpg")
                val uri = FileProvider.getUriForFile(context, context.packageName + ".files", file)
                photoUri = uri.toString()
                takePicture.launch(uri)
            }) { Text("Take a photo") }
            Spacer(Modifier.width(8.dp))
            Button(
                enabled = jpeg != null && !busy,
                onClick = {
                    val bytes = jpeg ?: return@Button
                    busy = true
                    status = "Reading the label…"
                    scope.launch {
                        try {
                            val read = session.call { it.extract(bytes) }
                            extraction = read
                            if (name.isBlank()) name = read.itemType.replaceFirstChar { it.uppercase() }
                            status = if (read.fromFixture) "Read by a recorded answer (fixture mode)." else "Read by ${read.model}."
                        } catch (e: Exception) {
                            status = "Could not read it: ${describe(e)}"
                        } finally {
                            busy = false
                        }
                    }
                },
            ) { Text(if (busy) "Working…" else "Read it") }
        }
        Spacer(Modifier.height(8.dp))
        preview?.let { Image(it.asImageBitmap(), contentDescription = "The photo", modifier = Modifier.fillMaxWidth()) }
        Text(status, style = MaterialTheme.typography.bodyMedium)
        extraction?.let { read ->
            Spacer(Modifier.height(12.dp))
            Text("A ${read.itemType.ifBlank { "device" }}", style = MaterialTheme.typography.titleMedium)
            for (f in read.fields) {
                val unit = if (f.unit.isNotBlank()) " ${f.unit}" else ""
                Text("${f.name.replace('_', ' ')}: ${f.value}$unit  (${(f.confidence * 100).toInt()}%, ${f.source})", style = MaterialTheme.typography.bodyMedium)
            }
            for (w in read.warnings) Text("Note: $w", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(value = condition, onValueChange = { condition = it }, label = { Text("Condition, in your words") }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))
            OutlinedButton(
                enabled = !busy && name.isNotBlank() && saved == null,
                onClick = {
                    busy = true
                    scope.launch {
                        try {
                            val item = session.call { it.saveItem(read, name.trim(), condition.trim()) }
                            saved = item
                            onSaved(item)
                            status = "Saved privately as item #${item.id}. Every value is yours to confirm on the web."
                        } catch (e: Exception) {
                            status = "Could not save: ${describe(e)}"
                        } finally {
                            busy = false
                        }
                    }
                },
            ) { Text(if (saved != null) "Saved as #${saved?.id}" else "Save privately") }
        }
    }
}

/** The photo as it is sent: decoded, turned the way the camera held it, scaled to at most
 * MAX_SIDE on the long side, re-encoded as a JPEG with nothing but pixels. */
private fun prepare(bytes: ByteArray?): Pair<ByteArray, Bitmap>? {
    if (bytes == null) return null
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / sample > MAX_SIDE * 2) sample *= 2
    val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample }) ?: return null
    val upright = turned(decoded, orientationOf(bytes))
    val longSide = maxOf(upright.width, upright.height)
    val scaled = if (longSide > MAX_SIDE) {
        val ratio = MAX_SIDE.toFloat() / longSide
        Bitmap.createScaledBitmap(upright, (upright.width * ratio).toInt(), (upright.height * ratio).toInt(), true)
    } else {
        upright
    }
    val out = ByteArrayOutputStream()
    scaled.compress(Bitmap.CompressFormat.JPEG, 88, out)
    return out.toByteArray() to scaled
}

private fun orientationOf(bytes: ByteArray): Int = try {
    ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
} catch (_: Exception) {
    ExifInterface.ORIENTATION_NORMAL
}

/** The pixels as the camera saw them, so the orientation tag is not needed and is not sent. */
private fun turned(bitmap: Bitmap, orientation: Int): Bitmap {
    val matrix = Matrix()
    when (orientation) {
        ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
        ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
        ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
        ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
        ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
        ExifInterface.ORIENTATION_TRANSPOSE -> { matrix.postRotate(90f); matrix.postScale(-1f, 1f) }
        ExifInterface.ORIENTATION_TRANSVERSE -> { matrix.postRotate(270f); matrix.postScale(-1f, 1f) }
        else -> return bitmap
    }
    return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
}
