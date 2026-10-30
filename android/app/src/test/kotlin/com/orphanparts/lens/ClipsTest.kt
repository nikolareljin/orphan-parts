package com.orphanparts.lens

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ClipsTest {
    private fun ftyp(brand: String): ByteArray =
        byteArrayOf(0, 0, 0, 24) + "ftyp".toByteArray(Charsets.ISO_8859_1) + brand.toByteArray(Charsets.ISO_8859_1) + ByteArray(8)

    @Test
    fun a_clip_is_an_mp4_or_3gp_by_its_brand_not_its_name() {
        assertTrue(looksLikeVideo(ftyp("isom")))
        assertTrue(looksLikeVideo(ftyp("mp42")))
        assertTrue(looksLikeVideo(ftyp("3gp4")))
        assertFalse(looksLikeVideo(ftyp("qt  "))) // a MOV
        assertFalse(looksLikeVideo(ftyp("heic"))) // a photo
        assertFalse(looksLikeVideo(ftyp("M4A "))) // audio
        assertFalse(looksLikeVideo("RIFF....WEBPVP8 ".toByteArray()))
        assertFalse(looksLikeVideo(ByteArray(4)))
    }
}
