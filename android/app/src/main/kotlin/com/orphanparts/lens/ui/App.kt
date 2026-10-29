package com.orphanparts.lens.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.orphanparts.lens.SettingsStore
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.HttpTransport

private val Scheme = lightColorScheme(
    primary = Color(0xFF1F4E5F),
    secondary = Color(0xFFF2B441),
    background = Color(0xFFFAF8F3),
    surface = Color(0xFFFFFFFF),
)

/** Three pages: where the backend is, a photo into the inventory, a voice note on an item. */
@Composable
fun App() {
    val context = LocalContext.current
    val store = remember { SettingsStore(context) }
    var settings by remember { mutableStateOf(store.load()) }
    var page by remember { mutableStateOf(if (settings.ready) 1 else 0) }
    var lastItemId by remember { mutableStateOf<Int?>(null) }
    var sent by remember { mutableStateOf(0) }

    // one client per settings: the session token it holds belongs to that backend and code
    val session = remember(settings) { Session(Client(settings.baseUrl, HttpTransport()), settings.accessCode, settings.token) }

    MaterialTheme(colorScheme = Scheme) {
        Scaffold { inner ->
            Column(Modifier.fillMaxSize().padding(inner)) {
                TabRow(selectedTabIndex = page) {
                    Tab(selected = page == 0, onClick = { page = 0 }, text = { Text("Backend") })
                    Tab(selected = page == 1, onClick = { page = 1 }, text = { Text("Capture") }, enabled = settings.ready)
                    Tab(selected = page == 2, onClick = { page = 2 }, text = { Text("Captures") }, enabled = settings.ready)
                    Tab(selected = page == 3, onClick = { page = 3 }, text = { Text("Talk") }, enabled = settings.ready)
                }
                Column(Modifier.padding(16.dp)) {
                    when (page) {
                        0 -> SettingsScreen(settings, session) { saved ->
                            store.save(saved)
                            settings = store.load()
                        }
                        1 -> CaptureScreen(session) { sent += 1 }
                        2 -> CapturesScreen(session, sent) { itemId ->
                            lastItemId = itemId
                            page = 3
                        }
                        else -> TalkScreen(session, lastItemId)
                    }
                }
            }
        }
    }
}
