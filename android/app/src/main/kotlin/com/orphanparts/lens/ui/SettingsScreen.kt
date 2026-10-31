package com.orphanparts.lens.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.orphanparts.lens.Settings
import com.orphanparts.lens.SettingsStore
import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.HttpTransport
import com.orphanparts.lens.api.Transport
import com.orphanparts.lens.isPairingToken
import com.orphanparts.lens.normalizeBaseUrl
import com.orphanparts.lens.pairingFrom
import com.orphanparts.lens.pointsAtLocalhost
import com.orphanparts.lens.tokenEnded
import com.orphanparts.lens.typedSettings
import com.orphanparts.lens.unpaired
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** What is typed is what is checked: the backend's open readiness path first, then the code
 * against the gate when there is one, each with its own line; a code of the phone's own is
 * named by its label and expiry, never shown. */
suspend fun check(
    baseUrl: String,
    code: String,
    token: String = "",
    own: Settings? = null,
    transport: Transport = HttpTransport(),
): String = withContext(Dispatchers.IO) {
    val client = Client(baseUrl, transport, token)
    val ready = try {
        client.readiness()
    } catch (e: Exception) {
        return@withContext "Not reachable: ${describe(e)}"
    }
    val gate = if (ready.gated) "gated" else "open"
    val line = "Backend ${ready.status}, Model API ${ready.modelApi}, demo $gate."
    val ownCode = own != null && own.ownCode
    when {
        !ready.gated -> line
        code.isBlank() && token.isNotBlank() -> try {
            // an ended token is served as the demo visitor, so its expiry is read first
            if (!tokenEnded(token) && client.accessGranted()) "$line Paired: the pairing works for a few minutes." else "$PAIRING_ENDED. $line"
        } catch (e: Exception) {
            "The pairing could not be checked: ${describe(e)}. $line"
        }
        code.isBlank() -> "$line Without the code this phone is the demo visitor: nothing it sends is kept."
        else -> try {
            val opens = client.access(code)
            when {
                opens && ownCode -> "$line The phone's own code (${own!!.codeName}) opens it."
                opens -> "$line The code opens it."
                else -> "The code is refused. $line"
            }
        } catch (e: ApiException) {
            if (e.status == 401 && ownCode) "${OWN_CODE_ENDED.replaceFirstChar { it.uppercase() }}. $line" else "The code is refused: ${describe(e)}. $line"
        }
    }
}

/** The phone's camera reads the pairing code the web app (or ./dev phone) shows; what it
 * carries becomes the settings, and one line says what happened. A code with a pairing is
 * saved at once, then the phone claims its own code with it in the process's scope and the
 * store is written again (the app observes it); a code without one (the demo visitor's page)
 * pairs the phone as the demo, keeping its own or typed code for the same backend. */
fun scanToPair(
    context: android.content.Context,
    store: SettingsStore,
    onSaved: (Settings) -> Unit,
    onStatus: (String) -> Unit,
) {
    val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
    GmsBarcodeScanning.getClient(context, options).startScan()
        .addOnSuccessListener { barcode ->
            val raw = barcode.rawValue ?: ""
            val before = store.load()
            val paired = pairingFrom(raw, before)
            if (paired == null) {
                onStatus(
                    if (pointsAtLocalhost(raw)) {
                        "Could not pair: that code points at localhost, which on the phone is the phone itself. Open the web app at the computer's network address and scan its code, or run ./dev phone."
                    } else {
                        "That code is not a pairing code."
                    },
                )
            } else {
                onSaved(paired)
                if (paired.token.isBlank()) {
                    val gated = json(raw).optBoolean("gated")
                    onStatus(
                        "Paired with ${paired.baseUrl}" + when {
                            !gated -> "."
                            paired.ownCode -> "; it keeps its own code (${paired.codeName})."
                            paired.accessCode.isNotBlank() -> "; it keeps the code typed on the Backend tab."
                            else -> " as the demo visitor: nothing it sends is kept. Sign in on the web app and scan its code to give this phone a code of its own."
                        },
                    )
                } else {
                    onStatus("Paired with ${paired.baseUrl}; getting this phone its own access code…")
                    startClaim(store, paired, before.baseUrl)
                }
            }
        }
        .addOnCanceledListener { onStatus("Scan canceled.") }
        .addOnFailureListener { e -> onStatus("Could not scan: ${e.message ?: e.javaClass.simpleName}") }
}

private fun json(text: String): JSONObject = try { JSONObject(text) } catch (_: Exception) { JSONObject() }

/** Unpair: the phone is released from the backend from its own side. The backend is asked
 * once to forget the session (`DELETE /api/access`, what Sign out calls; a backend that keeps
 * the session in a cookie drops it, ours stores nothing, so the token runs to its own expiry)
 * with a short wait and whatever comes back, then what the pairing left is emptied: the
 * address, the code, the token, the code's label and expiry. The phone's own code is not
 * revoked here, the app has no right to; `./dev keys revoke` on the server does that, by its
 * label, and the dialog says so. */
suspend fun unpair(held: Settings, transport: Transport = HttpTransport(readMs = 5_000, connectMs = 5_000)): Settings =
    withContext(Dispatchers.IO) {
        if (held.ready && held.token.isNotBlank()) {
            try {
                Client(held.baseUrl, transport, held.token).leave()
            } catch (_: Exception) {
                // the phone forgets the session either way
            }
        }
        unpaired(held)
    }

/** What the Unpair dialog asks: the phone's own code is named by its label with where it is
 * revoked, since unpairing leaves it issued; a typed code or a pairing has nothing to revoke. */
fun unpairQuestion(held: Settings): String =
    if (held.ownCode) {
        "Unpair this phone? It forgets the address, its code and its session. The code stays valid on the server until it is revoked there: ./dev keys revoke \"${held.codeLabel}\""
    } else {
        "Unpair this phone? It forgets the address, the code and the session it holds."
    }

@Composable
fun SettingsScreen(
    settings: Settings,
    store: SettingsStore,
    note: Pair<Int, String> = 0 to "", // a line from elsewhere (the header's scan) to show
    onSaved: (Settings) -> Unit,
) {
    val context = LocalContext.current
    // keyed on what the fields show: a background write of the token (a claim's session, a
    // refreshed one) leaves unsaved typing alone
    var url by remember(settings.baseUrl, settings.accessCode) { mutableStateOf(settings.baseUrl) }
    var code by remember(settings.baseUrl, settings.accessCode) { mutableStateOf(settings.accessCode) }
    var status by remember { mutableStateOf("") }
    var askUnpair by remember { mutableStateOf(false) }
    LaunchedEffect(note) { if (note.second.isNotEmpty()) status = note.second }
    val scope = rememberCoroutineScope()
    val muted = MaterialTheme.colorScheme.onSurfaceVariant

    Column {
        Panel {
            Text("Where the inventory lives", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(6.dp))
            Text(
                "The same backend as the web app. Scan the code the web app shows under Pair the phone, or type the address. Photos, clips and notes go there and nowhere else.",
                style = MaterialTheme.typography.bodyMedium,
                color = muted,
            )
            Spacer(Modifier.height(12.dp))
            PrimaryButton("Scan to pair") { scanToPair(context, store, onSaved) { status = it } }
        }
        Spacer(Modifier.height(12.dp))
        Panel {
            Text("Or type it", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("Backend URL") },
                placeholder = { Text("http://192.168.1.20:5173") },
                singleLine = true,
                colors = fieldColors(),
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = code,
                onValueChange = { code = it },
                label = { Text("Access code (without it you get the demo)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                colors = fieldColors(),
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            )
            if (settings.ownCode && code == settings.accessCode && normalizeBaseUrl(url) == settings.baseUrl) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "This phone holds a code of its own, ${settings.codeName}; it ends with ./dev keys revoke \"${settings.codeLabel}\" on the server, or when the code that paired it ends.",
                    style = MaterialTheme.typography.bodySmall,
                    color = muted,
                )
            } else if (isPairingToken(settings.token) && !tokenEnded(settings.token)) {
                Spacer(Modifier.height(6.dp))
                Text("Paired for a few minutes; scan the code again when it ends.", style = MaterialTheme.typography.bodySmall, color = muted)
            }
            Spacer(Modifier.height(12.dp))
            Row {
                PrimaryButton("Save") {
                    onSaved(typedSettings(settings, url, code))
                    status = "Saved."
                }
                Spacer(Modifier.width(8.dp))
                SecondaryButton("Check", enabled = url.isNotBlank()) {
                    status = "Checking…"
                    val typedUrl = normalizeBaseUrl(url)
                    val typedCode = code
                    // the token in hand counts for the address and the code it was opened with
                    val pairing = if (typedUrl == settings.baseUrl && typedCode == settings.accessCode) settings.token else ""
                    val own = if (typedUrl == settings.baseUrl && typedCode == settings.accessCode) settings else null
                    scope.launch { status = check(typedUrl, typedCode, pairing, own) }
                }
                // anything a pairing or a Save left can be released
                if (settings.baseUrl.isNotBlank() || settings.accessCode.isNotBlank() || settings.token.isNotBlank()) {
                    Spacer(Modifier.width(8.dp))
                    SecondaryButton("Unpair", tone = Tone.Error) { askUnpair = true }
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        StatusLine(status)
    }

    if (askUnpair) {
        val colors = MaterialTheme.colorScheme
        AlertDialog(
            onDismissRequest = { askUnpair = false },
            title = { Text("Unpair") },
            text = { Text(unpairQuestion(settings)) },
            containerColor = colors.surface,
            titleContentColor = colors.onSurface,
            textContentColor = colors.onSurfaceVariant,
            shape = MaterialTheme.shapes.large,
            confirmButton = {
                TextButton(onClick = {
                    askUnpair = false
                    status = "Unpairing…"
                    val held = settings
                    scope.launch {
                        val empty = unpair(held)
                        // a claim still running goes first, then the store is emptied on disk
                        // before anything else, so the pairing cannot come back with the next
                        // start; the app observes the store, as for a claim
                        forgetClaims()
                        store.save(empty, durable = true)
                        status = "Unpaired."
                    }
                }) { Text("Unpair", color = colors.error) }
            },
            dismissButton = { TextButton(onClick = { askUnpair = false }) { Text("Keep", color = colors.primary) } },
        )
    }
}
