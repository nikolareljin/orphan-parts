package com.orphanparts.lens.ui

import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.tokenEnded
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** The backend's line for a call the demo visitor may not make; an ended or refused session is
 * served as the demo visitor, so this is how a write says the token in hand no longer opens. */
const val DEMO_REFUSAL = "demo:"
const val PAIRING_ENDED = "the pairing has ended; scan the code again"
const val CLAIM_ENDED = "the pairing has ended; reload the signed-in page and scan its new code"
const val OWN_CODE_ENDED = "this phone's code has ended or was revoked; scan the code on a signed-in page"

/** The client and what opens the backend: the token in hand (a pairing, or a session opened
 * with the code) while it has not ended by its own expiry and the backend still grants it, the
 * code otherwise. The backend answers an ended or revoked session as the demo visitor, not
 * with a 401: reads answer what the demo sees and writes are refused with the demo line. So
 * the token's expiry is read here, the token is asked about once (`GET /api/access`, an open
 * path that costs no attempt) before it is used, and a demo refusal (or a 401) opens a new
 * session with the code once, when there is one. A code the backend refuses with 401 stays
 * refused for this session: it is not sent again, since every try counts against the
 * address's attempts, and `onCodeEnded` hears of the phone's own code ending. A connection
 * that breaks is opened again too: a stale token on an upload can end the connection before
 * the answer is read, and the next call must not fail the same way. */
class Session(
    val client: Client,
    private val accessCode: String,
    private val heldToken: String = "",
    private val ownCode: Boolean = false,
    private val now: () -> Long = { System.currentTimeMillis() / 1000 },
    private val onCodeEnded: () -> Unit = {},
) {
    private var opened = false
    private var refusedCode: ApiException? = null

    /** Whether this phone has a way through the code's door: a code, or a token still current.
     * Without one a gated backend treats it as the demo visitor and keeps nothing it sends. */
    val hasDoor: Boolean get() = accessCode.isNotBlank() || (heldToken.isNotBlank() && !tokenEnded(heldToken, now()))

    suspend fun <T> call(block: (Client) -> T): T = withContext(Dispatchers.IO) {
        refusedCode?.let { throw it }
        if (!opened) open()
        try {
            block(client)
        } catch (e: ApiException) {
            if (!refused(e)) throw e
            if (accessCode.isBlank()) {
                if (heldToken.isNotBlank()) throw ApiException(e.status, PAIRING_ENDED)
                throw e
            }
            opened = false
            open(afterRefusal = true)
            block(client)
        } catch (e: IOException) {
            opened = false
            throw e
        }
    }

    private fun refused(e: ApiException): Boolean =
        e.status == 401 || (e.status == 403 && e.message.orEmpty().startsWith(DEMO_REFUSAL))

    private fun open(afterRefusal: Boolean = false) {
        if (heldToken.isNotBlank() && !afterRefusal && !tokenEnded(heldToken, now()) && granted(heldToken)) {
            opened = true
            return
        }
        when {
            accessCode.isNotBlank() -> try {
                client.access(accessCode)
            } catch (e: ApiException) {
                if (e.status != 401) throw e
                val ended = if (ownCode) ApiException(401, OWN_CODE_ENDED) else e
                refusedCode = ended
                if (ownCode) onCodeEnded()
                throw ended
            }
            // an ended pairing and no code: the demo visitor, which the backend says on a write
            else -> client.useToken("")
        }
        opened = true
    }

    /** Whether the backend still grants the token: a revoked one reads as the demo visitor
     * without a word. A backend that cannot say keeps the token, and a write says the rest. */
    private fun granted(token: String): Boolean {
        client.useToken(token)
        return try {
            client.accessGranted()
        } catch (_: ApiException) {
            true
        }
    }
}

fun describe(e: Throwable): String = when (e) {
    is ApiException -> "${e.message} (HTTP ${e.status})"
    else -> e.message ?: e.javaClass.simpleName
}
