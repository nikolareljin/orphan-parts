package com.orphanparts.lens.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import com.orphanparts.lens.normalizeBaseUrl
import com.orphanparts.lens.pairingFrom
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(settings: Settings, session: Session, onSaved: (Settings) -> Unit) {
    val context = LocalContext.current
    var url by remember(settings) { mutableStateOf(settings.baseUrl) }
    var code by remember(settings) { mutableStateOf(settings.accessCode) }
    var status by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    Column {
        Text("Where the inventory lives", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        Text(
            "The same backend as the web app. Scan the code the web app shows under Pair the phone, or type the address. Photos, clips and notes go there and nowhere else.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(12.dp))
        Button(onClick = {
            val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
            GmsBarcodeScanning.getClient(context, options).startScan()
                .addOnSuccessListener { barcode ->
                    val paired = pairingFrom(barcode.rawValue ?: "", settings)
                    if (paired == null) {
                        status = "That code is not a pairing code."
                    } else {
                        onSaved(paired)
                        status = "Paired with ${paired.baseUrl}" + (if (paired.token.isNotBlank()) " (with a session)." else ".")
                    }
                }
                .addOnCanceledListener { status = "Scan cancelled." }
                .addOnFailureListener { e -> status = "Could not scan: ${e.message ?: e.javaClass.simpleName}" }
        }) { Text("Scan to pair") }
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("Backend URL") },
            placeholder = { Text("http://192.168.1.20:5173") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = code,
            onValueChange = { code = it },
            label = { Text("Access code (when the demo is gated)") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        if (settings.token.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            Text("A session from the pairing is kept; it ends on its own, scan again then.", style = MaterialTheme.typography.bodySmall)
        }
        Spacer(Modifier.height(16.dp))
        Row {
            Button(onClick = {
                onSaved(Settings(normalizeBaseUrl(url), code, token = if (normalizeBaseUrl(url) == settings.baseUrl) settings.token else ""))
                status = "Saved."
            }) { Text("Save") }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(
                enabled = settings.ready,
                onClick = {
                    status = "Checking…"
                    scope.launch {
                        status = try {
                            val ready = session.call { it.readiness() }
                            val gate = if (ready.gated) "gated" else "open"
                            "Backend ${ready.status}, Model API ${ready.modelApi}, demo $gate."
                        } catch (e: Exception) {
                            "Not reachable: ${describe(e)}"
                        }
                    }
                },
            ) { Text("Check") }
        }
        Spacer(Modifier.height(8.dp))
        Text(status, style = MaterialTheme.typography.bodyMedium)
    }
}
