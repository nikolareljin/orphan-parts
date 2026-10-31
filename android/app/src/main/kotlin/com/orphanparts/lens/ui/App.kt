package com.orphanparts.lens.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.orphanparts.lens.R
import com.orphanparts.lens.SettingsStore
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.HttpTransport
import com.orphanparts.lens.api.Readiness

private val PAGES = listOf("Backend", "Capture", "Captures", "Talk")

/** What the service line at the foot says, from a readiness answer or its absence. */
fun serviceLine(baseUrl: String, ready: Readiness?, error: String?): String {
    if (baseUrl.isBlank()) return "No backend yet: pair the phone or type the address."
    val host = baseUrl.removePrefix("https://").removePrefix("http://")
    if (ready == null) return "$host · ${error ?: "checking…"}"
    val answers = if (ready.modelApi.startsWith("fixture")) "recorded answers (nothing spent)" else "live models"
    val gate = if (ready.gated) "demo gated" else "demo open"
    return "$host · $answers · $gate"
}

/** Four pages under one header, in the web app's look: the mark and the name, the pages as
 * tabs, the service line at the foot. */
@Composable
fun App() {
    val context = LocalContext.current
    val store = remember { SettingsStore(context) }
    var settings by remember { mutableStateOf(store.load()) }
    var page by remember { mutableStateOf(if (settings.ready) 1 else 0) }
    var lastItemId by remember { mutableStateOf<Int?>(null) }
    var sent by remember { mutableStateOf(0) }
    var service by remember { mutableStateOf(serviceLine("", null, null)) }
    // what the header's scan said, numbered so the same line twice is shown twice
    var pairLine by remember { mutableStateOf(0 to "") }
    // shown on the Backend tab once: leaving the tab clears it, so a return does not replay it
    LaunchedEffect(page) { if (page != 0 && pairLine.second.isNotEmpty()) pairLine = pairLine.first to "" }

    // one client per settings: the token it holds belongs to that backend and code
    val session = remember(settings) {
        Session(Client(settings.baseUrl, HttpTransport()), settings.accessCode, settings.token, settings.ownCode)
    }
    // a claim finished (in the process's scope, stored there): the settings are read again, and
    // the line shown on the Backend tab without moving to it
    val claimed: (String) -> Unit = { line ->
        settings = store.load()
        pairLine = pairLine.first + 1 to line
    }
    LaunchedEffect(Unit) { retryClaimAtStart(store, claimed) }

    LaunchedEffect(session) {
        service = serviceLine(settings.baseUrl, null, null)
        if (!settings.ready) return@LaunchedEffect
        service = try {
            serviceLine(settings.baseUrl, session.call { it.readiness() }, null)
        } catch (e: Exception) {
            serviceLine(settings.baseUrl, null, "not reachable: ${describe(e)}")
        }
    }

    OrphanPartsTheme {
        val colors = MaterialTheme.colorScheme
        Scaffold(containerColor = colors.background) { inner ->
            Column(Modifier.fillMaxSize().background(colors.background).padding(inner)) {
                Row(
                    Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Image(
                        painterResource(R.mipmap.ic_launcher_foreground),
                        contentDescription = null,
                        modifier = Modifier.size(44.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Orphan Parts Lens", style = MaterialTheme.typography.titleLarge, color = colors.onBackground)
                        Text(
                            "Show it, ask it, sell it, or find the one that fits.",
                            style = MaterialTheme.typography.bodySmall,
                            color = colors.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    // pair again from any page: the scanner, then the Backend tab shows the outcome
                    QrButton {
                        scanToPair(context, store, onSaved = { saved ->
                            store.save(saved)
                            settings = store.load()
                        }, onClaimed = claimed) { line ->
                            pairLine = pairLine.first + 1 to line
                            page = 0
                        }
                    }
                }
                TabRow(
                    selectedTabIndex = page,
                    containerColor = colors.background,
                    contentColor = colors.onSurfaceVariant,
                    indicator = { positions ->
                        TabRowDefaults.SecondaryIndicator(
                            Modifier.tabIndicatorOffset(positions[page]),
                            height = 2.dp,
                            color = colors.primary,
                        )
                    },
                    divider = { HorizontalDivider(color = colors.outline) },
                ) {
                    for ((index, label) in PAGES.withIndex()) {
                        Tab(
                            selected = page == index,
                            onClick = { page = index },
                            enabled = index == 0 || settings.ready,
                            selectedContentColor = colors.primary,
                            unselectedContentColor = colors.onSurfaceVariant,
                            text = { Text(label, fontWeight = FontWeight.Medium) },
                        )
                    }
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
                    when (page) {
                        0 -> SettingsScreen(settings, store, pairLine, onSaved = { saved ->
                            store.save(saved)
                            settings = store.load()
                        }, onClaimed = claimed)
                        1 -> CaptureScreen(session) { sent += 1 }
                        2 -> CapturesScreen(session, sent) { itemId ->
                            lastItemId = itemId
                            page = 3
                        }
                        else -> TalkScreen(session, lastItemId)
                    }
                }
                ServiceLine(service)
            }
        }
    }
}
