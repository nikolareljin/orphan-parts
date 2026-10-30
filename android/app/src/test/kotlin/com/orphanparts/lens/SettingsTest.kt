package com.orphanparts.lens

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
