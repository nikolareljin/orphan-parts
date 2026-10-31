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
    private val own = Settings("https://demo.example", "opl_mine", "sid.1.sig", "phone abcd1234", "2026-11-29T10:00:00+00:00")

    @Test
    fun a_pairing_code_for_the_same_backend_sets_the_token_and_keeps_the_code() {
        val current = Settings("http://192.168.1.20:5173", "the code", "")
        val paired = pairingFrom("""{"url":"http://192.168.1.20:5173/","gated":true,"token":"sid.1.sig"}""", current)!!
        assertEquals("http://192.168.1.20:5173", paired.baseUrl)
        assertEquals("sid.1.sig", paired.token)
        assertEquals("the code", paired.accessCode)
    }

    @Test
    fun a_signed_in_code_for_another_backend_drops_the_code_it_held() {
        val paired = pairingFrom("""{"url":"https://elsewhere.example","gated":true,"token":"sid.2.sig"}""", own)!!
        assertEquals(Settings("https://elsewhere.example", "", "sid.2.sig"), paired)
        assertFalse(paired.ownCode)
        // an open backend elsewhere gets no code either
        val open = pairingFrom("""{"url":"https://open.example","gated":false,"token":""}""", Settings("http://old:8000", "typed"))!!
        assertEquals(Settings("https://open.example", ""), open)
    }

    @Test
    fun a_demo_code_for_the_same_backend_keeps_the_phones_own_code() {
        val demo = pairingFrom("""{"url":"https://demo.example","gated":true,"token":""}""", own)!!
        assertEquals(own.copy(token = ""), demo)
        assertTrue(demo.ownCode)
    }

    @Test
    fun a_demo_code_for_another_backend_pairs_the_phone_as_the_demo_visitor() {
        val demo = pairingFrom("""{"url":"https://other.example","gated":true,"token":""}""", own)!!
        assertEquals(Settings("https://other.example", ""), demo)
        assertFalse(demo.ownCode)
        // a later scan of a signed-in page carries a pairing again
        val signedIn = pairingFrom("""{"url":"https://other.example","gated":true,"token":"sid.2.sig"}""", demo)!!
        assertEquals("sid.2.sig", signedIn.token)
        assertEquals("", signedIn.accessCode)
    }

    @Test
    fun the_claimed_code_replaces_the_typed_one_and_is_named_by_its_label() {
        val paired = Settings("https://demo.example", "typed", "sid.1.sig")
        assertFalse(paired.ownCode)
        val own = withPhoneCode(paired, PhoneCode(true, "opl_mine", "phone abcd1234", "2026-11-29T10:00:00+00:00"))
        assertEquals("opl_mine", own.accessCode)
        assertTrue(own.ownCode)
        assertEquals("phone abcd1234", own.codeLabel)
        assertEquals("2026-11-29", own.codeExpiresDay)
        assertEquals("phone abcd1234, until 2026-11-29", own.codeName)
        assertEquals("phone abcd1234", own.copy(codeExpires = "").codeName)
    }

    @Test
    fun save_keeps_the_label_and_the_token_only_for_the_same_address_and_code() {
        assertEquals(own, typedSettings(own, "https://demo.example/", "opl_mine"))
        assertEquals(Settings("https://demo.example", "typed"), typedSettings(own, "https://demo.example", "typed"))
        assertEquals(Settings("http://elsewhere.example", "opl_mine"), typedSettings(own, "elsewhere.example", "opl_mine"))
    }

    @Test
    fun a_claim_lands_only_on_the_scan_it_started_from() {
        val scanned = Settings("https://demo.example", "", "sid.1.sig")
        val claimed = own
        assertEquals(claimed, applyClaim(scanned, scanned, claimed))
        assertNull(applyClaim(scanned.copy(token = "sid.2.sig"), scanned, claimed))
        assertNull(applyClaim(scanned.copy(baseUrl = "https://other.example"), scanned, claimed))
    }

    @Test
    fun a_token_is_read_for_its_expiry_and_its_kind() {
        val pairing = "sid.2000.2.0.0123456789abcdef.${"a".repeat(32)}"
        assertEquals(2000L, tokenExpiry(pairing))
        assertFalse(tokenEnded(pairing, 1999))
        assertTrue(tokenEnded(pairing, 2000))
        assertTrue(tokenEnded("nonsense", 0))
        assertTrue(isPairingToken(pairing))
        assertFalse(isPairingToken("sid.2000.1.0.0123456789abcdef.${"a".repeat(32)}"))
        // the shape before the binding: five fields, read for its expiry, never a pairing
        val old = "sid.3000.1.0.${"b".repeat(32)}"
        assertEquals(3000L, tokenExpiry(old))
        assertFalse(isPairingToken(old))
        assertFalse(isPairingToken("sid.3000.2.0.${"b".repeat(32)}"))
    }

    @Test
    fun an_ended_own_code_leaves_the_store_without_a_code() {
        val held = Settings("https://demo.example", "opl_mine", "sid.9.1.0.x", "phone abcd1234", "2026-12-01")
        assertEquals(Settings("https://demo.example", ""), withoutEndedCode(held, "opl_mine"))
        // a code saved since, or a typed one, stays
        assertNull(withoutEndedCode(held.copy(accessCode = "opl_newer"), "opl_mine"))
        assertNull(withoutEndedCode(Settings("https://demo.example", "opl_mine"), "opl_mine"))
        // a live pairing from a scan since stays for its claim; an ended one goes
        val live = "sid.9999999999.2.0.0123456789abcdef.${"a".repeat(32)}"
        assertEquals(Settings("https://demo.example", "", live), withoutEndedCode(held.copy(token = live), "opl_mine"))
        val ended = "sid.9.2.0.0123456789abcdef.${"a".repeat(32)}"
        assertEquals(Settings("https://demo.example", ""), withoutEndedCode(held.copy(token = ended), "opl_mine"))
        // the live pairing that claimed the ended code is spent: it goes too
        val spent = "abcd1234xyz.9999999999.2.0.0123456789abcdef.${"a".repeat(32)}"
        assertEquals(Settings("https://demo.example", ""), withoutEndedCode(held.copy(token = spent), "opl_mine"))
    }

    @Test
    fun an_unpaired_phone_holds_nothing_and_takes_nothing_from_before() {
        val empty = unpaired(own)
        assertEquals(Settings("", ""), empty)
        assertFalse(empty.ready)
        assertFalse(empty.ownCode)
        assertEquals(Settings("", ""), unpaired(Settings("http://host:8000", "typed", "sid.1.sig")))
        // a claim started before the unpair lands on nothing: the scan it came from is gone
        val scanned = Settings("https://demo.example", "", "sid.1.sig")
        assertNull(applyClaim(empty, scanned, own))
        assertNull(applyClaim(empty, scanned.copy(token = ""), own))
        // and a code heard of as ended after it changes nothing
        assertNull(withoutEndedCode(empty, "opl_mine"))
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
