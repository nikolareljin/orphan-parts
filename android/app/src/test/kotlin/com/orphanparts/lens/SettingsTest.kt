package com.orphanparts.lens

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import org.junit.Test

class SettingsTest {
    @Test
    fun a_base_url_gets_a_scheme_and_loses_the_trailing_slash_and_api_path() {
        assertEquals("http://192.168.1.20:8000", normalizeBaseUrl(" 192.168.1.20:8000/ "))
        assertEquals("https://demo.example", normalizeBaseUrl("https://demo.example/api/"))
        assertEquals("http://host:8000", normalizeBaseUrl("http://host:8000"))
        assertEquals("", normalizeBaseUrl("   "))
    }

    @Test
    fun settings_are_ready_once_a_url_is_set() {
        assertFalse(Settings("", "").ready)
        assertTrue(Settings("http://host:8000", "").ready)
    }
}

class PairingTest {
    @Test
    fun a_pairing_code_sets_the_url_and_the_session_and_keeps_the_code() {
        val current = Settings("http://old:8000", "the code", "")
        val paired = pairingFrom("""{"url":"http://192.168.1.20:5173","gated":true,"token":"sid.1.sig"}""", current)!!
        assertEquals("http://192.168.1.20:5173", paired.baseUrl)
        assertEquals("sid.1.sig", paired.token)
        assertEquals("the code", paired.accessCode)
        val open = pairingFrom("""{"url":"https://demo.example/","gated":false,"token":""}""", current)!!
        assertEquals("https://demo.example", open.baseUrl)
        assertEquals("", open.token)
    }

    @Test
    fun anything_else_is_not_a_pairing_code() {
        val current = Settings("", "", "")
        assertNull(pairingFrom("hello", current))
        assertNull(pairingFrom("""{"token":"x"}""", current))
        assertNull(pairingFrom("""{"url":"http://somebody.example/app"}""", current))
        assertNull(pairingFrom("", current))
    }
}
