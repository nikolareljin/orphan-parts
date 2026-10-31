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
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** After a scan that carried a pairing: the phone's own code from the backend, then a session
 * opened with that code, which replaces the pairing (it lasts minutes; the code lasts days).
 * A code of its own for the same backend (`previousUrl` unchanged) that still opens the door
 * is kept rather than claimed again; only a 401 from the backend says it does not, so a
 * network error or a busy backend leaves it in place. A refused claim (the pairing already
 * claimed, the code that paired it ended, a browser's session) leaves the pairing. The code
 * claimed goes to `keep` as soon as it arrives, with the pairing still as the token, before
 * the session is asked for: the backend never hands it out again. */
suspend fun claimPhoneCode(
    paired: Settings,
    previousUrl: String,
    transport: Transport,
    keep: (Settings) -> Unit = {},
): Pair<Settings, String> =
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
            val why = if (e is ApiException && e.status == 401) CLAIM_ENDED else describe(e)
            return@withContext paired to "$where (with a pairing); no code of its own: $why."
        }
        if (!own.gated || own.code.isBlank()) return@withContext paired to "$where."
        val claimed = withPhoneCode(paired, own)
        withContext(NonCancellable) { keep(claimed) }
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
 * written to the store whatever happens to the caller, and the UI observes the store, so an
 * Activity created since sees it too. */
private val claims = CoroutineScope(SupervisorJob() + Dispatchers.IO)
private var retriedAtStart = false

/** The line of the last claim stored, for the Backend tab: the UI shows it and empties it. */
val claimLine = MutableStateFlow("")

/** The claim for a scan, run in the process's scope; the outcome is stored, on disk before
 * anything else, only if the settings still hold the scan it came from, and only then is its
 * line set (a later scan or a typed address says its own). The code is written twice: on disk
 * as soon as it is claimed, the pairing still its token so the scan still matches, and again
 * with the session opened with it. */
fun startClaim(
    store: SettingsStore,
    paired: Settings,
    previousUrl: String,
    transport: Transport = HttpTransport(),
): Job = claims.launch {
    val keep = { claimed: Settings ->
        applyClaim(store.load(), paired, claimed)?.also { store.save(it, durable = true) }
    }
    val (claimed, line) = claimPhoneCode(paired, previousUrl, transport) { keep(it) }
    val applied = withContext(NonCancellable) { keep(claimed) }
    if (applied != null) claimLine.value = line
}

/** On an unpair: what a pairing left outside the store goes too. A claim still running is
 * canceled (its outcome would land on the emptied store and not apply, by `applyClaim`), and
 * a line not yet shown is dropped. */
fun forgetClaims() {
    claims.coroutineContext.cancelChildren()
    claimLine.value = ""
}

/** Whether the settings hold a claim the app was closed during: a pairing still current with
 * no code of its own claimed. */
fun shouldRetryClaim(held: Settings, nowSeconds: Long = System.currentTimeMillis() / 1000): Boolean =
    held.ready && !held.ownCode && isPairingToken(held.token) && !tokenEnded(held.token, nowSeconds)

/** On the first start of the process: a claim the app was closed during is claimed once more. */
fun retryClaimAtStart(store: SettingsStore) {
    if (retriedAtStart) return
    retriedAtStart = true
    val held = store.load()
    if (shouldRetryClaim(held)) startClaim(store, held, held.baseUrl)
}
