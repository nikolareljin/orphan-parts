package com.orphanparts.lens.ui

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import java.io.File

/** The device question for one item, as the web app's ParentPrompt asks it: the item as the
 * backend last served it, a call in flight, the last refusal in the server's words (and whether
 * it was a photo's), and what a photo of the device gave (`null` until one is sent). */
data class DeviceAnswer(
    val item: ItemView? = null,
    val busy: Boolean = false,
    val error: String = "",
    val photoFailed: Boolean = false,
    val photoModel: String? = null,
) {
    /** The backend asks (`needs_parent`) and the item is the owner's, not the visitor's view. */
    val asks: Boolean get() = item?.needsParent == true && !item.redacted

    /** Once answered: the model as read or typed, and the owner's words; empty when neither. */
    val cameFrom: String
        get() = listOfNotNull(item?.parentDeviceModel, item?.parentDevice).filter { it.isNotBlank() }.joinToString(", ")

    /** Shown for the owner's item: the backend marks the demo visitor's view `redacted` (and
     * answers a private item with 404), so an ungated backend, where every caller is the owner,
     * gets the question too. */
    val shown: Boolean get() = item != null && !item.redacted && (asks || cameFrom.isNotEmpty())

    /** A photo picked: busy from now until it is read, so a second pick meanwhile is refused
     * (`null`) and cannot send a second paid reading. */
    fun startPhoto(): DeviceAnswer? = if (busy) null else copy(busy = true, error = "", photoFailed = false)
}

/** The item read again; a refusal leaves the card as it was, with nothing said. */
suspend fun loadDevice(session: Session, itemId: Int, state: DeviceAnswer): DeviceAnswer = try {
    state.copy(item = session.call { it.item(itemId) }, error = "")
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    state
}

/** The owner's words about the device, saved as `parent_device`; a refusal is said as the server said it. */
suspend fun answerDevice(session: Session, itemId: Int, state: DeviceAnswer, words: String): DeviceAnswer {
    val value = words.trim()
    if (value.isEmpty()) return state.copy(busy = false)
    return try {
        state.copy(item = session.call { it.setParentDevice(itemId, value) }, busy = false, error = "", photoFailed = false)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        state.copy(busy = false, error = describe(e), photoFailed = false)
    }
}

/** A photo of the device, read on the backend; the model it gave is kept to say it. */
suspend fun photographDevice(session: Session, itemId: Int, state: DeviceAnswer, jpeg: ByteArray): DeviceAnswer = try {
    val read = session.call { it.parentPhoto(itemId, jpeg) }
    state.copy(item = read.item, busy = false, error = "", photoFailed = false, photoModel = read.model)
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    state.copy(busy = false, error = describe(e), photoFailed = true)
}

/** The device answers of the Captures tab, one per item, kept for the session so a tab switch
 * asks nothing again: each item is read once (a failed read too, until Refresh), at most
 * [LOADS_AT_ONCE] at a time. */
class DeviceAnswers(private val session: Session) {
    private val answers = HashMap<Int, DeviceAnswer>()
    private val limit = Semaphore(LOADS_AT_ONCE)

    fun cached(itemId: Int): DeviceAnswer? = answers[itemId]

    fun put(itemId: Int, state: DeviceAnswer) {
        answers[itemId] = state
    }

    /** The answer for the item: the one kept, or one read now and kept. */
    suspend fun load(itemId: Int): DeviceAnswer {
        answers[itemId]?.let { return it }
        val read = limit.withPermit { answers[itemId] ?: loadDevice(session, itemId, DeviceAnswer()) }
        return answers.getOrPut(itemId) { read }
    }

    /** Forgets every answer, so the next look reads the items again. */
    fun clear() = answers.clear()

    companion object {
        const val LOADS_AT_ONCE = 2
    }
}

/** Under a capture read into an item: the question when the backend asks it, *Came from: ...*
 * once it is answered, nothing otherwise and nothing for the demo visitor's view. */
@Composable
fun DeviceQuestionCard(answers: DeviceAnswers, session: Session, itemId: Int) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember(itemId) { mutableStateOf(answers.cached(itemId) ?: DeviceAnswer()) }
    var words by rememberSaveable(itemId) { mutableStateOf("") }
    // kept across a process death while the camera app is in front, so the photo still lands
    var pendingUri by rememberSaveable(itemId) { mutableStateOf<String?>(null) }
    var unreadable by remember(itemId) { mutableStateOf(false) }
    val colors = MaterialTheme.colorScheme

    fun update(next: DeviceAnswer) {
        state = next
        answers.put(itemId, next)
    }

    LaunchedEffect(answers, itemId) { state = answers.load(itemId) }

    // busy from the pick on, so a second pick while this one is read cannot send a second photo
    fun send(uri: Uri, camera: Boolean) {
        update(state.startPhoto() ?: return)
        unreadable = false
        scope.launch {
            val prepared = withContext(Dispatchers.IO) {
                try {
                    preparePhoto(context.contentResolver.openInputStream(uri)?.use { it.readBytes() })
                } catch (e: Exception) {
                    null
                } catch (e: OutOfMemoryError) {
                    null
                }
            }
            try {
                if (prepared == null) {
                    unreadable = true
                    update(state.copy(busy = false))
                } else {
                    update(photographDevice(session, itemId, state, prepared.first))
                }
            } finally {
                // the camera's file is the app's own copy: gone once sent or refused
                if (camera) forget(context, uri)
            }
        }
    }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = pendingUri?.let(Uri::parse)
        pendingUri = null
        if (uri == null) return@rememberLauncherForActivityResult
        if (ok) send(uri, camera = true) else forget(context, uri)
    }
    val pickPhoto = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) send(uri, camera = false)
    }

    if (!state.shown) return
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
                update(state.copy(busy = true, error = ""))
                scope.launch {
                    update(answerDevice(session, itemId, state, words))
                    if (state.error.isEmpty()) words = ""
                }
            }
            Spacer(Modifier.height(8.dp))
            // one under the other: two buttons side by side do not fit a narrow phone
            SecondaryButton(stringResource(R.string.device_photo), enabled = !state.busy) {
                val dir = File(context.cacheDir, "captures").apply { mkdirs() }
                val uri = FileProvider.getUriForFile(context, context.packageName + ".files", File(dir, "device-${System.currentTimeMillis()}.jpg"))
                pendingUri = uri.toString()
                takePicture.launch(uri)
            }
            Spacer(Modifier.height(8.dp))
            SecondaryButton(stringResource(R.string.device_photo_gallery), enabled = !state.busy) {
                pickPhoto.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
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
            StatusLine(stringResource(if (state.photoFailed) R.string.device_photo_failed else R.string.device_failed, state.error))
        }
    }
}

/** The camera's file in the app's cache, removed; one already gone is fine. */
private fun forget(context: Context, uri: Uri) {
    try {
        context.contentResolver.delete(uri, null, null)
    } catch (_: Exception) {
        // nothing to remove
    }
}
