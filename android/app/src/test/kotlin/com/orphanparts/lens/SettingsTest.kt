package com.orphanparts.lens

import com.orphanparts.lens.api.PhoneCode
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
        assertEquals("the code", open.accessCode)
    }

    @Test
    fun a_gated_code_without_a_session_pairs_the_phone_as_the_demo_visitor() {
        val current = Settings("http://old:8000", "opl_old", "sid.1.sig", "phone abcd1234", "2026-11-29T10:00:00+00:00")
        val demo = pairingFrom("""{"url":"https://demo.example","gated":true,"token":""}""", current)!!
        assertEquals(Settings("https://demo.example", ""), demo)
        assertFalse(demo.ownCode)
        // a later scan of a signed-in page carries a session again
        val signedIn = pairingFrom("""{"url":"https://demo.example","gated":true,"token":"sid.2.sig"}""", demo)!!
        assertEquals("sid.2.sig", signedIn.token)
        assertEquals("", signedIn.accessCode)
    }

    @Test
    fun the_claimed_code_replaces_the_typed_one_and_is_named_by_its_label() {
        val paired = Settings("https://demo.example", "typed", "sid.1.sig")
        assertFalse(paired.ownCode)
        val own = withPhoneCode(paired, PhoneCode(true, "opl_mine", "phone abcd1234", "2026-11-29T10:00:00+00:00"))
        assertEquals("opl_mine", own.accessCode)
        assertEquals("sid.1.sig", own.token)
        assertTrue(own.ownCode)
        assertEquals("phone abcd1234", own.codeLabel)
        assertEquals("2026-11-29", own.codeExpiresDay)
        // a typed code over it is a typed code again
        assertFalse(own.copy(accessCode = "other", codeLabel = "", codeExpires = "").ownCode)
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

class ReachableTest {
    @Test
    fun a_pairing_code_that_points_at_localhost_is_refused_and_said() {
        val current = Settings("", "", "")
        assertNull(pairingFrom("""{"url":"http://localhost:5183","gated":false,"token":""}""", current))
        assertNull(pairingFrom("""{"url":"http://127.0.0.1:8000","gated":false,"token":""}""", current))
        assertTrue(pointsAtLocalhost("""{"url":"http://localhost:5183","gated":false,"token":""}"""))
        assertTrue(pointsAtLocalhost("""{"url":"http://127.0.0.2:5183","gated":true,"token":"t"}"""))
        assertFalse(pointsAtLocalhost("""{"url":"http://192.168.1.20:5183","gated":false,"token":""}"""))
        assertFalse(pointsAtLocalhost("""{"url":"http://localhost:5183"}""")) // not a pairing code
        assertFalse(pointsAtLocalhost("not json"))
        assertTrue(reachableFromAPhone("https://orphan-parts.pages.dev"))
        assertTrue(reachableFromAPhone("http://192.168.1.20:5183"))
        assertTrue(reachableFromAPhone("http://[2001:db8::1]:5183"))
        assertFalse(reachableFromAPhone("http://[::1]:5183"))
        assertFalse(reachableFromAPhone("http://[::ffff:127.0.0.1]:5183"))
        assertFalse(reachableFromAPhone("http://[0:0:0:0:0:0:0:1]:5183"))
        assertTrue(reachableFromAPhone("http://127.1:5183")) // not a dotted quad: a name, checked later
        assertFalse(reachableFromAPhone("http://[::]:5183"))
        assertTrue(reachableFromAPhone("http://my_laptop:5183"))
        assertFalse(reachableFromAPhone("http://127.0.0.2:5183"))
        assertFalse(reachableFromAPhone("http://0.0.0.0:5183"))
        assertFalse(reachableFromAPhone("http://app.localhost:5183"))
        assertFalse(reachableFromAPhone("not a url"))
    }
}
