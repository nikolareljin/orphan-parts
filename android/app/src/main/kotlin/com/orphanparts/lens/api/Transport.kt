package com.orphanparts.lens.api

import java.io.ByteArrayOutputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL

/** One HTTP exchange, as the client sees it. */
data class HttpResponse(val status: Int, val body: String) {
    val ok: Boolean get() = status in 200..299
}

/** A request body written to the connection as it goes, its length known up front. */
interface Body {
    val contentType: String
    val length: Long
    fun writeTo(out: OutputStream)
}

/** The thing that sends bytes; the real one below, a fake in tests. A fake needs only the
 * bytes form: a streamed body is given to it in memory. */
interface Transport {
    fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse

    fun send(method: String, url: String, headers: Map<String, String>, body: Body): HttpResponse {
        val out = ByteArrayOutputStream()
        body.writeTo(out)
        return send(method, url, headers, out.toByteArray())
    }
}

/** A reading can take the backend a minute on its own (the model's limit is 60 s), so the
 * phone waits longer than that for an answer before it gives up and the backend spends for
 * nothing; a connection that does not open is given up on quickly, so a wrong address is
 * said in seconds. */
class HttpTransport(private val readMs: Int = 120_000, private val connectMs: Int = 10_000) : Transport {
    override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse =
        exchange(method, url, headers, body?.size?.toLong()) { out -> if (body != null) out.write(body) }

    override fun send(method: String, url: String, headers: Map<String, String>, body: Body): HttpResponse =
        exchange(method, url, headers, body.length) { out -> body.writeTo(out) }

    private fun exchange(method: String, url: String, headers: Map<String, String>, length: Long?, write: (OutputStream) -> Unit): HttpResponse {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = connectMs
            connection.readTimeout = readMs
            connection.setRequestProperty("Accept", "application/json")
            for ((name, value) in headers) connection.setRequestProperty(name, value)
            if (length != null) {
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(length)
                connection.outputStream.use(write)
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
