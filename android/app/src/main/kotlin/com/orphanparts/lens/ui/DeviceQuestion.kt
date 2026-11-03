package com.orphanparts.lens.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.orphanparts.lens.R
import com.orphanparts.lens.api.ItemView
import com.orphanparts.lens.preparePhoto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** The device question for one item, as the web app's ParentPrompt asks it: the item as the
 * backend last served it, a call in flight, the last refusal in the server's words, and what a
 * photo of the device gave (`null` until one is sent). */
data class DeviceAnswer(
    val item: ItemView? = null,
    val busy: Boolean = false,
    val error: String = "",
    val photoModel: String? = null,
) {
    /** The backend asks (`needs_parent`) and the item is the owner's, not the visitor's view. */
    val asks: Boolean get() = item?.needsParent == true && !item.redacted

    /** Once answered: the model as read or typed, and the owner's words; empty when neither. */
    val cameFrom: String
        get() = listOfNotNull(item?.parentDeviceModel, item?.parentDevice).filter { it.isNotBlank() }.joinToString(", ")

    /** Shown only to a phone with a way through the code's door: without one the backend
     * answers it as the demo visitor, which gets the question with nothing to fill in. */
    fun shown(hasDoor: Boolean): Boolean = hasDoor && item != null && !item.redacted && (asks || cameFrom.isNotEmpty())
}

/** The item read again; a refusal leaves the card as it was, with nothing said. */
suspend fun loadDevice(session: Session, itemId: Int, state: DeviceAnswer): DeviceAnswer = try {
    state.copy(item = session.call { it.item(itemId) }, error = "")
} catch (e: Exception) {
    state
}

/** The owner's words about the device, saved as `parent_device`; a refusal is said as the server said it. */
suspend fun answerDevice(session: Session, itemId: Int, state: DeviceAnswer, words: String): DeviceAnswer {
    val value = words.trim()
    if (value.isEmpty()) return state
    return try {
        state.copy(item = session.call { it.setParentDevice(itemId, value) }, busy = false, error = "")
    } catch (e: Exception) {
        state.copy(busy = false, error = describe(e))
    }
}

/** A photo of the device, read on the backend; the model it gave is kept to say it. */
suspend fun photographDevice(session: Session, itemId: Int, state: DeviceAnswer, jpeg: ByteArray): DeviceAnswer = try {
    val read = session.call { it.parentPhoto(itemId, jpeg) }
    state.copy(item = read.item, busy = false, error = "", photoModel = read.model)
} catch (e: Exception) {
    state.copy(busy = false, error = describe(e))
}

/** Under a capture read into an item: the question when the backend asks it, *Came from: ...*
 * once it is answered, nothing otherwise and nothing without a code or a pairing. */
@Composable
fun DeviceQuestionCard(session: Session, itemId: Int) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember(itemId) { mutableStateOf(DeviceAnswer()) }
    var words by rememberSaveable(itemId) { mutableStateOf("") }
    // kept across a process death while the camera app is in front, so the photo still lands
    var pendingUri by rememberSaveable(itemId) { mutableStateOf<String?>(null) }
    var unreadable by remember(itemId) { mutableStateOf(false) }
    val colors = MaterialTheme.colorScheme

    LaunchedEffect(session, itemId) {
        if (session.hasDoor) state = loadDevice(session, itemId, state)
    }

    fun send(bytes: ByteArray?) {
        scope.launch {
            val prepared = withContext(Dispatchers.IO) {
                try {
                    preparePhoto(bytes)
                } catch (e: Exception) {
                    null
                } catch (e: OutOfMemoryError) {
                    null
                }
            }
            if (prepared == null) {
                unreadable = true
                return@launch
            }
            unreadable = false
            state = state.copy(busy = true, error = "")
            state = photographDevice(session, itemId, state, prepared.first)
        }
    }

    fun read(uri: Uri?): ByteArray? = try {
        uri?.let { context.contentResolver.openInputStream(it)?.use { input -> input.readBytes() } }
    } catch (e: Exception) {
        null
    } catch (e: OutOfMemoryError) {
        null
    }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = pendingUri?.let(Uri::parse)
        if (ok && uri != null) scope.launch { send(withContext(Dispatchers.IO) { read(uri) }) }
    }
    val pickPhoto = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch { send(withContext(Dispatchers.IO) { read(uri) }) }
    }

    if (!state.shown(session.hasDoor)) return
    Spacer(Modifier.height(10.dp))
    if (!state.asks) {
        Text(stringResource(R.string.device_came_from, state.cameFrom), style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
    } else {
        Panel {
            Text(stringResource(R.string.device_question), style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = words,
                onValueChange = { words = it.take(500) },
                label = { Text(stringResource(R.string.device_field)) },
                placeholder = { Text(stringResource(R.string.device_field_hint)) },
                singleLine = true,
                enabled = !state.busy,
                colors = fieldColors(),
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            PrimaryButton(stringResource(R.string.device_save), enabled = !state.busy && words.isNotBlank()) {
                state = state.copy(busy = true, error = "")
                scope.launch {
                    state = answerDevice(session, itemId, state, words)
                    if (state.error.isEmpty()) words = ""
                }
            }
            Spacer(Modifier.height(8.dp))
            Row {
                SecondaryButton(stringResource(R.string.device_photo), enabled = !state.busy) {
                    val dir = File(context.cacheDir, "captures").apply { mkdirs() }
                    val uri = FileProvider.getUriForFile(context, context.packageName + ".files", File(dir, "device-${System.currentTimeMillis()}.jpg"))
                    pendingUri = uri.toString()
                    takePicture.launch(uri)
                }
                Spacer(Modifier.width(8.dp))
                SecondaryButton(stringResource(R.string.device_photo_gallery), enabled = !state.busy) {
                    pickPhoto.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                stringResource(if (state.busy) R.string.device_reading else R.string.device_photo_hint),
                style = MaterialTheme.typography.bodySmall,
                color = colors.onSurfaceVariant,
            )
        }
    }
    Column {
        state.photoModel?.let { model ->
            Spacer(Modifier.height(6.dp))
            val line = if (model.isNotBlank()) stringResource(R.string.device_photo_read, model) else stringResource(R.string.device_photo_none)
            Text(line, style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
        }
        if (unreadable) {
            Spacer(Modifier.height(6.dp))
            StatusLine(stringResource(R.string.device_photo_unreadable))
        }
        if (state.error.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            StatusLine(stringResource(R.string.device_failed, state.error))
        }
    }
}
