package com.orphanparts.lens.api

import java.io.ByteArrayOutputStream
import java.io.OutputStream

/** A multipart/form-data body, built by hand: the uploads are photos, a clip, a recording and
 * a JSON field, nothing a library is needed for. The parts are kept as they are and written
 * straight to the connection: a clip near the size the backend takes is never copied. */
class Multipart(private val boundary: String = "opl-" + System.nanoTime().toString(36)) : Body {
    private sealed class Part(val head: ByteArray) {
        abstract val size: Long
        abstract fun write(out: OutputStream)
    }

    private class Bytes(head: ByteArray, val bytes: ByteArray) : Part(head) {
        override val size: Long get() = bytes.size.toLong()
        override fun write(out: OutputStream) = out.write(bytes)
    }

    private val parts = mutableListOf<Part>()
    private val crlf = "\r\n".toByteArray(Charsets.UTF_8)
    private val tail = "--$boundary--\r\n".toByteArray(Charsets.UTF_8)

    override val contentType: String get() = "multipart/form-data; boundary=$boundary"

    override val length: Long
        get() = parts.sumOf { it.head.size + it.size + crlf.size } + tail.size

    fun text(name: String, value: String): Multipart {
        val head = "--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n".toByteArray(Charsets.UTF_8)
        parts += Bytes(head, value.toByteArray(Charsets.UTF_8))
        return this
    }

    fun file(name: String, fileName: String, mime: String, bytes: ByteArray): Multipart {
        val head = (
            "--$boundary\r\nContent-Disposition: form-data; name=\"$name\"; filename=\"$fileName\"\r\n" +
                "Content-Type: $mime\r\n\r\n"
            ).toByteArray(Charsets.UTF_8)
        parts += Bytes(head, bytes)
        return this
    }

    override fun writeTo(out: OutputStream) {
        for (part in parts) {
            out.write(part.head)
            part.write(out)
            out.write(crlf)
        }
        out.write(tail)
    }

    /** The whole body in memory: for small bodies and the tests. */
    fun bytes(): ByteArray {
        val out = ByteArrayOutputStream()
        writeTo(out)
        return out.toByteArray()
    }
}
