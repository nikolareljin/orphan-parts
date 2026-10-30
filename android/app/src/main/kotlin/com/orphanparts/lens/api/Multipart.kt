package com.orphanparts.lens.api

import java.io.ByteArrayOutputStream

/** A multipart/form-data body, built by hand: the uploads are a photo or a recording and a
 * JSON field, nothing a library is needed for. */
class Multipart(private val boundary: String = "opl-" + System.nanoTime().toString(36)) {
    private val out = ByteArrayOutputStream()

    val contentType: String get() = "multipart/form-data; boundary=$boundary"

    fun text(name: String, value: String): Multipart {
        write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n")
        write(value)
        write("\r\n")
        return this
    }

    fun file(name: String, fileName: String, mime: String, bytes: ByteArray): Multipart {
        write(
            "--$boundary\r\nContent-Disposition: form-data; name=\"$name\"; filename=\"$fileName\"\r\n" +
                "Content-Type: $mime\r\n\r\n",
        )
        out.write(bytes)
        write("\r\n")
        return this
    }

    fun bytes(): ByteArray {
        val copy = ByteArrayOutputStream()
        out.writeTo(copy)
        copy.write("--$boundary--\r\n".toByteArray(Charsets.UTF_8))
        return copy.toByteArray()
    }

    private fun write(text: String) {
        out.write(text.toByteArray(Charsets.UTF_8))
    }
}
