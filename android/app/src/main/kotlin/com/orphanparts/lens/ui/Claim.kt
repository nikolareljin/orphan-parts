package com.orphanparts.lens.ui

import com.orphanparts.lens.Settings
import com.orphanparts.lens.SettingsStore
import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.HttpTransport
import com.orphanparts.lens.api.Transport
import com.orphanparts.lens.applyClaim
import com.orphanparts.lens.isPairingToken
import com.orphanparts.lens.tokenEnded
import com.orphanparts.lens.withPhoneCode
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** After a scan that carried a pairing: the phone's own code from the backend, then a session
 * opened with that code, which replaces the pairing (it lasts minutes; the code lasts days).
 * A code of its own for the same backend (`previousUrl` unchanged) that still opens the door
 * is kept rather than claimed again; only a 401 from the backend says it does not, so a
 * network error or a busy backend leaves it in place. A refused claim (the pairing already
 * claimed, the code that paired it ended, a browser's session) leaves the pairing. */
suspend fun claimPhoneCode(paired: Settings, previousUrl: String, transport: Transport): Pair<Settings, String> =
    withContext(Dispatchers.IO) {
        val where = "Paired with ${paired.baseUrl}"
        val client = Client(paired.baseUrl, transport)
        if (paired.ownCode && paired.baseUrl == previousUrl) {
            val opened = try {
                if (client.access(paired.accessCode)) client.token else null
            } catch (e: ApiException) {
                if (e.status == 401) null else return@withContext paired to "$where; it keeps its own code (${paired.codeName}): ${describe(e)}."
            } catch (e: Exception) {
                return@withContext paired to "$where; it keeps its own code (${paired.codeName}): ${describe(e)}."
            }
            if (opened != null) return@withContext paired.copy(token = opened) to "$where; it keeps its own code (${paired.codeName})."
        }
        client.useToken(paired.token)
        val own = try {
            client.phoneCode()
        } catch (e: Exception) {
            return@withContext paired to "$where (with a pairing); no code of its own: ${describe(e)}."
        }
        if (!own.gated || own.code.isBlank()) return@withContext paired to "$where."
        val claimed = withPhoneCode(paired, own)
        val line = "$where; this phone now has a code of its own (${claimed.codeName})."
        // the pairing is spent: a session opened with the code takes its place, or none, and the
        // next call opens one
        val session = try {
            if (client.access(own.code)) client.token else ""
        } catch (_: Exception) {
            ""
        }
        claimed.copy(token = session) to line
    }

/** Claims outlive the screen that started them: the scope is the process's, the result is
 * written to the store whatever happens to the caller, and the UI reads the store again. */
private val claims = CoroutineScope(SupervisorJob() + Dispatchers.IO)
private var retriedAtStart = false

/** The claim for a scan, run in the process's scope; the outcome is stored only if the
 * settings still hold the scan it came from, then `onDone` gets the line on the main thread. */
fun startClaim(
    store: SettingsStore,
    paired: Settings,
    previousUrl: String,
    transport: Transport = HttpTransport(),
    onDone: (String) -> Unit,
): Job = claims.launch {
    val (claimed, line) = claimPhoneCode(paired, previousUrl, transport)
    withContext(NonCancellable) {
        applyClaim(store.load(), paired, claimed)?.let { store.save(it) }
    }
    withContext(Dispatchers.Main) { onDone(line) }
}

/** On the first start of the process: a pairing still current with no code of its own claimed
 * (the app was closed while it claimed) is claimed once more. */
fun retryClaimAtStart(store: SettingsStore, onDone: (String) -> Unit) {
    if (retriedAtStart) return
    retriedAtStart = true
    val held = store.load()
    if (!held.ready || held.ownCode || !isPairingToken(held.token) || tokenEnded(held.token)) return
    startClaim(store, held, held.baseUrl, onDone = onDone)
}
