package com.orphanparts.lens.audio

import org.junit.Assert.assertEquals
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class WavTest {
    @Test
    fun the_header_says_pcm_mono_16_bit_and_the_sizes() {
        val header = wavHeader(16_000, 1, 16, 32_000)
        assertEquals(44, header.size)
        assertEquals("RIFF", String(header, 0, 4, Charsets.US_ASCII))
        assertEquals("WAVE", String(header, 8, 4, Charsets.US_ASCII))
        assertEquals("fmt ", String(header, 12, 4, Charsets.US_ASCII))
        assertEquals("data", String(header, 36, 4, Charsets.US_ASCII))
        val b = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(36 + 32_000, b.getInt(4))
        assertEquals(1, b.getShort(20).toInt())
        assertEquals(1, b.getShort(22).toInt())
        assertEquals(16_000, b.getInt(24))
        assertEquals(32_000, b.getInt(28))
        assertEquals(2, b.getShort(32).toInt())
        assertEquals(16, b.getShort(34).toInt())
        assertEquals(32_000, b.getInt(40))
    }

    @Test
    fun a_file_is_the_header_then_the_samples_and_its_length_is_known() {
        val pcm = ByteArray(3_200) { it.toByte() }
        val file = wavFile(16_000, 1, 16, pcm)
        assertEquals(44 + 3_200, file.size)
        assertEquals(pcm.toList(), file.copyOfRange(44, file.size).toList())
        assertEquals(0.1, wavSeconds(16_000, 1, 16, 3_200), 1e-9)
    }
}
