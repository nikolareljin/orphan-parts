package com.orphanparts.lens.api

import org.junit.Assert.assertEquals
import org.junit.Test

class MultipartTest {
    @Test
    fun parts_are_framed_by_the_boundary_and_closed() {
        val body = Multipart("B").text("request", "{\"a\":1}").file("audio", "n.wav", "audio/wav", byteArrayOf(0, 1)).bytes()
        val text = String(body, Charsets.ISO_8859_1)
        val expected = "--B\r\nContent-Disposition: form-data; name=\"request\"\r\n\r\n{\"a\":1}\r\n" +
            "--B\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"n.wav\"\r\nContent-Type: audio/wav\r\n\r\n\u0000\u0001\r\n" +
            "--B--\r\n"
        assertEquals(expected, text)
        assertEquals("multipart/form-data; boundary=B", Multipart("B").contentType)
    }
}
