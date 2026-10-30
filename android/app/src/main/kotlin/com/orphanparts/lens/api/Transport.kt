package com.orphanparts.lens.api

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** One HTTP exchange, as the client sees it. */
data class HttpResponse(val status: Int, val body: String) {
    val ok: Boolean get() = status in 200..299
}

/** The thing that sends bytes; the real one below, a fake in tests. */
interface Transport {
    fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse
}

class HttpTransport(private val timeoutMs: Int = 60_000) : Transport {
    override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = timeoutMs
            connection.readTimeout = timeoutMs
            connection.setRequestProperty("Accept", "application/json")
            for ((name, value) in headers) connection.setRequestProperty(name, value)
            if (body != null) {
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.use { input ->
                val out = ByteArrayOutputStream()
                input.copyTo(out)
                out.toString("UTF-8")
            } ?: ""
            return HttpResponse(status, text)
        } finally {
            connection.disconnect()
        }
    }
}
