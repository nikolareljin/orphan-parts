package com.orphanparts.lens.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
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

    suspend fun load() {
        try {
            captures = session.call { it.captures() }
            status = if (captures.isEmpty()) "Nothing sent yet." else ""
        } catch (e: Exception) {
            status = "Could not list the captures: ${describe(e)}"
        }
    }

    LaunchedEffect(refresh) { load() }

    Column(Modifier.verticalScroll(rememberScrollState())) {
        Row {
            Text("Captures", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.width(12.dp))
            OutlinedButton(onClick = { scope.launch { load() } }) { Text("Refresh") }
        }
        Spacer(Modifier.height(8.dp))
        Text(status, style = MaterialTheme.typography.bodyMedium)
        for (c in captures) {
            HorizontalDivider()
            Spacer(Modifier.height(8.dp))
            Text("#${c.id} · ${c.createdAt.take(16).replace('T', ' ')}", style = MaterialTheme.typography.titleMedium)
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
            )
            Spacer(Modifier.height(6.dp))
            Row {
                if (c.status != "processed") {
                    Button(
                        enabled = busyId == null,
                        onClick = {
                            busyId = c.id
                            scope.launch {
                                try {
                                    session.call { it.processCapture(c.id) }
                                    load()
                                } catch (e: Exception) {
                                    status = "Capture #${c.id}: ${describe(e)}"
                                } finally {
                                    busyId = null
                                }
                            }
                        },
                    ) { Text(if (busyId == c.id) "Reading…" else if (c.status == "failed") "Try again" else "Read it now") }
                } else {
                    OutlinedButton(onClick = { c.itemId?.let(onItem) }) { Text("Talk about item #${c.itemId}") }
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}
