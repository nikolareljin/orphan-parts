package com.orphanparts.lens.ui

import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** The client and what opens the backend: a session from the pairing when there is one, the
 * demo code otherwise. A session is opened once, and again after a 401. */
class Session(val client: Client, private val accessCode: String, private val pairedToken: String = "") {
    private var opened = false

    suspend fun <T> call(block: (Client) -> T): T = withContext(Dispatchers.IO) {
        if (!opened) open()
        try {
            block(client)
        } catch (e: ApiException) {
            if (e.status != 401) throw e
            opened = false
            open(afterRefusal = true)
            block(client)
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
