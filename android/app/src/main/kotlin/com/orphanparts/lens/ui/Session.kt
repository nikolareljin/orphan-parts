package com.orphanparts.lens.ui

import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** The client with the demo code: a session is opened once, and again after a 401. */
class Session(val client: Client, private val accessCode: String) {
    private var opened = false

    suspend fun <T> call(block: (Client) -> T): T = withContext(Dispatchers.IO) {
        if (!opened) open()
        try {
            block(client)
        } catch (e: ApiException) {
            if (e.status != 401) throw e
            opened = false
            open()
            block(client)
        }
    }

    private fun open() {
        if (accessCode.isNotBlank()) client.access(accessCode)
        opened = true
    }
}

fun describe(e: Throwable): String = when (e) {
    is ApiException -> "${e.message} (HTTP ${e.status})"
    else -> e.message ?: e.javaClass.simpleName
}
