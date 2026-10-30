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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.orphanparts.lens.Settings
import com.orphanparts.lens.normalizeBaseUrl
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(settings: Settings, session: Session, onSaved: (Settings) -> Unit) {
    var url by remember(settings) { mutableStateOf(settings.baseUrl) }
    var code by remember(settings) { mutableStateOf(settings.accessCode) }
    var status by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    Column {
        Text("Where the inventory lives", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        Text("The same backend as the web app. Photos and voice notes go there and nowhere else.", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("Backend URL") },
            placeholder = { Text("http://192.168.1.20:8000") },
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
        Spacer(Modifier.height(16.dp))
        Row {
            Button(onClick = {
                onSaved(Settings(normalizeBaseUrl(url), code))
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
