package com.orphanparts.lens.ui

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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.orphanparts.lens.Settings
import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.HttpTransport
import com.orphanparts.lens.normalizeBaseUrl
import com.orphanparts.lens.pairingFrom
import com.orphanparts.lens.pointsAtLocalhost
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** What is typed is what is checked: the backend's open readiness path first, then the code
 * against the gate when there is one, each with its own line. */
suspend fun check(baseUrl: String, code: String, token: String = ""): String = withContext(Dispatchers.IO) {
    val client = Client(baseUrl, HttpTransport(), token)
    val ready = try {
        client.readiness()
    } catch (e: Exception) {
        return@withContext "Not reachable: ${describe(e)}"
    }
    val gate = if (ready.gated) "gated" else "open"
    val line = "Backend ${ready.status}, Model API ${ready.modelApi}, demo $gate."
    when {
        !ready.gated -> line
        code.isBlank() && token.isNotBlank() -> try {
            if (client.accessGranted()) "$line Paired: the session works until it ends." else "$line The pairing has ended; scan the code again."
        } catch (e: Exception) {
            "$line The pairing could not be checked: ${describe(e)}"
        }
        code.isBlank() -> "$line Without the code this phone is the demo visitor: nothing it sends is kept."
        else -> try {
            if (client.access(code)) "$line The code opens it." else "$line The code is refused."
        } catch (e: ApiException) {
            "$line The code is refused: ${describe(e)}"
        }
    }
}

/** The phone's camera reads the pairing code the web app (or ./dev phone) shows; what it
 * carries becomes the settings, and one line says what happened. */
fun scanToPair(context: android.content.Context, settings: Settings, onSaved: (Settings) -> Unit, onStatus: (String) -> Unit) {
    val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
    GmsBarcodeScanning.getClient(context, options).startScan()
        .addOnSuccessListener { barcode ->
            val raw = barcode.rawValue ?: ""
            val paired = pairingFrom(raw, settings)
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
                onStatus("Paired with ${paired.baseUrl}" + (if (paired.token.isNotBlank()) " (with a session)." else "."))
            }
        }
        .addOnCanceledListener { onStatus("Scan canceled.") }
        .addOnFailureListener { e -> onStatus("Could not scan: ${e.message ?: e.javaClass.simpleName}") }
}

@Composable
fun SettingsScreen(
    settings: Settings,
    session: Session,
    note: Pair<Int, String> = 0 to "", // a line from elsewhere (the header's scan) to show
    onSaved: (Settings) -> Unit,
) {
    val context = LocalContext.current
    var url by remember(settings) { mutableStateOf(settings.baseUrl) }
    var code by remember(settings) { mutableStateOf(settings.accessCode) }
    var status by remember { mutableStateOf("") }
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
            PrimaryButton("Scan to pair") { scanToPair(context, settings, onSaved) { status = it } }
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
                label = { Text("Access code (the live door; without it a gated backend is a demo)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                colors = fieldColors(),
                shape = MaterialTheme.shapes.small,
                modifier = Modifier.fillMaxWidth(),
            )
            if (settings.token.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text("A session from the pairing is kept; it ends on its own, scan again then.", style = MaterialTheme.typography.bodySmall, color = muted)
            }
            Spacer(Modifier.height(12.dp))
            Row {
                PrimaryButton("Save") {
                    onSaved(Settings(normalizeBaseUrl(url), code, token = if (normalizeBaseUrl(url) == settings.baseUrl) settings.token else ""))
                    status = "Saved."
                }
                Spacer(Modifier.width(8.dp))
                SecondaryButton("Check", enabled = url.isNotBlank()) {
                    status = "Checking…"
                    val typedUrl = normalizeBaseUrl(url)
                    val typedCode = code
                    // the pairing's session counts for the address it was made for
                    val pairing = if (typedUrl == settings.baseUrl) settings.token else ""
                    scope.launch { status = check(typedUrl, typedCode, pairing) }
                }
            }
        }
        Spacer(Modifier.height(10.dp))
        StatusLine(status)
    }
}
