package com.orphanparts.lens.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.orphanparts.lens.api.Capture
import kotlinx.coroutines.launch

/** What was sent, and whether the backend has read it into an item yet. */
@Composable
fun CapturesScreen(session: Session, refresh: Int, onItem: (Int) -> Unit) {
    val scope = rememberCoroutineScope()
    var captures by remember { mutableStateOf<List<Capture>>(emptyList()) }
    var status by remember { mutableStateOf("") }
    var busyId by remember { mutableStateOf<Int?>(null) }
    val muted = MaterialTheme.colorScheme.onSurfaceVariant

    suspend fun load() {
        try {
            captures = session.call { it.captures() }
            status = if (captures.isEmpty()) "Nothing sent yet." else ""
        } catch (e: Exception) {
            status = "Could not list the captures: ${describe(e)}"
        }
    }

    LaunchedEffect(refresh) { load() }

    Column {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Captures", style = MaterialTheme.typography.titleLarge)
            SecondaryButton("Refresh") { scope.launch { load() } }
        }
        Spacer(Modifier.height(8.dp))
        StatusLine(status)
        for (c in captures) {
            Spacer(Modifier.height(10.dp))
            Panel {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("#${c.id} · ${c.createdAt.take(16).replace('T', ' ')}", style = MaterialTheme.typography.titleMedium)
                    when (c.status) {
                        "processed" -> Pill("read", Tone.Accent)
                        "failed" -> Pill("not read", Tone.Error)
                        else -> Pill("received")
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "${c.photos} photo(s)${if (c.clip) ", a clip" else ""}${if (c.audio) ", a note (${"%.0f".format(c.audioSeconds)} s)" else ""}" +
                        (if (c.name.isNotBlank()) " · ${c.name}" else "") + (if (c.note.isNotBlank()) " · ${c.note}" else ""),
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    when (c.status) {
                        "processed" -> "Read into item #${c.itemId}" + (if (c.model.isNotBlank()) " by ${c.model}" else "")
                        "failed" -> "Could not be read: ${c.error}"
                        else -> "Received, not read yet"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (c.status == "failed") MaterialTheme.colorScheme.error else muted,
                )
                Spacer(Modifier.height(10.dp))
                if (c.status != "processed") {
                    PrimaryButton(
                        if (busyId == c.id) "Reading…" else if (c.status == "failed") "Try again" else "Read it now",
                        enabled = busyId == null,
                    ) {
                        busyId = c.id
                        scope.launch {
                            try {
                                session.call { it.processCapture(c.id) }
                            } catch (e: Exception) {
                                status = "Capture #${c.id}: ${describe(e)}"
                            } finally {
                                // the list again either way: a failed read is recorded on the capture
                                load()
                                busyId = null
                            }
                        }
                    }
                } else {
                    SecondaryButton("Talk about item #${c.itemId}") { c.itemId?.let(onItem) }
                }
            }
        }
    }
}
