package com.orphanparts.lens.ui

import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** The client and what opens the backend: a session from the pairing when there is one, the
 * demo code otherwise. A session is opened once, and again after a 401. A connection that
 * breaks is opened again too: a stale token on an upload can end the connection before the
 * 401 is read, and the next call must not fail the same way. */
class Session(val client: Client, private val accessCode: String, private val pairedToken: String = "") {
    private var opened = false

    /** Whether this phone has a way through the code's door: a code typed, or a pairing. Without
     * one a gated backend treats it as the demo visitor and keeps nothing it sends. */
    val hasDoor: Boolean get() = accessCode.isNotBlank() || pairedToken.isNotBlank()

    suspend fun <T> call(block: (Client) -> T): T = withContext(Dispatchers.IO) {
        if (!opened) open()
        try {
            block(client)
        } catch (e: ApiException) {
            if (e.status != 401) throw e
            opened = false
            open(afterRefusal = true)
            block(client)
        } catch (e: IOException) {
            opened = false
            throw e
        }
    }

    private fun open(afterRefusal: Boolean = false) {
        when {
            pairedToken.isNotBlank() && !afterRefusal -> client.useToken(pairedToken)
            accessCode.isNotBlank() -> client.access(accessCode)
            pairedToken.isNotBlank() -> throw ApiException(401, "the pairing has ended; scan the code again")
        }
        opened = true
    }
}

fun describe(e: Throwable): String = when (e) {
    is ApiException -> "${e.message} (HTTP ${e.status})"
    else -> e.message ?: e.javaClass.simpleName
}
