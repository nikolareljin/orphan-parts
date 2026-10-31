package com.orphanparts.lens.ui

import com.orphanparts.lens.Settings
import com.orphanparts.lens.api.FakeTransport
import com.orphanparts.lens.api.HttpResponse
import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ClaimTest {
    private val url = "https://demo.example"
    private val pairing = "sid.9999999999.2.0.0123456789abcdef.${"a".repeat(32)}"
    private val own = Settings(url, "opl_mine", pairing, "phone abcd1234", "2026-11-29T10:00:00+00:00")
    private val claimed = HttpResponse(200, """{"gated":true,"code":"opl_new","label":"phone ffff0000","expires_at":"2026-12-01T00:00:00+00:00"}""")
    private val opened = HttpResponse(200, """{"gated":true,"granted":true,"token":"code.session","expires_at":1}""")

    /** A transport that answers from a script, and throws for an answer of null. */
    private fun transport(vararg answers: HttpResponse?): FakeTransport {
        val queue = ArrayDeque(answers.toList())
        return object : FakeTransport(ArrayDeque()) {
            override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
                sent += Sent(method, url, headers, body)
                return queue.removeFirst() ?: throw IOException("network is unreachable")
            }
        }
    }

    @Test
    fun an_own_code_that_still_opens_is_kept_and_its_session_replaces_the_pairing() = runBlocking {
        val t = transport(opened)
        val (kept, line) = claimPhoneCode(own, url, t)
        assertEquals(own.copy(token = "code.session"), kept)
        assertTrue(line.contains("keeps its own code (phone abcd1234, until 2026-11-29)"))
        assertEquals(1, t.sent.size)
    }

    @Test
    fun a_refused_own_code_is_replaced_by_a_new_claim_with_a_session_of_its_own() = runBlocking {
        val t = transport(HttpResponse(401, """{"detail":"that is not the access code"}"""), claimed, opened)
        val (next, line) = claimPhoneCode(own, url, t)
        assertEquals("opl_new", next.accessCode)
        assertEquals("phone ffff0000", next.codeLabel)
        assertEquals("code.session", next.token)
        assertEquals("https://demo.example/api/pair/code", t.sent[1].url)
        assertEquals("Bearer $pairing", t.sent[1].headers["Authorization"])
        assertTrue(line.contains("now has a code of its own (phone ffff0000, until 2026-12-01)"))
    }

    @Test
    fun a_network_error_keeps_the_code_it_has() = runBlocking {
        val t = transport(null)
        val (kept, line) = claimPhoneCode(own, url, t)
        assertEquals(own, kept)
        assertTrue(line.contains("keeps its own code"))
        // and a busy backend too: only a 401 says the code no longer opens
        val (busy, _) = claimPhoneCode(own, url, transport(HttpResponse(429, """{"detail":"too many tries; wait 9 s"}""")))
        assertEquals(own, busy)
    }

    @Test
    fun a_refused_claim_leaves_the_pairing() = runBlocking {
        val paired = Settings(url, "", pairing)
        val t = transport(HttpResponse(403, """{"detail":"a code was issued for 'phone sid' already"}"""))
        val (left, line) = claimPhoneCode(paired, url, t)
        assertEquals(paired, left)
        assertTrue(line.contains("no code of its own: a code was issued"))
    }

    @Test
    fun a_kept_code_is_tried_only_for_the_same_backend() = runBlocking {
        val t = transport(claimed, opened)
        val (next, _) = claimPhoneCode(own, "http://other:5173", t)
        assertEquals("https://demo.example/api/pair/code", t.sent[0].url)
        assertEquals("opl_new", next.accessCode)
    }

    @Test
    fun without_an_expiry_the_line_leaves_out_until() = runBlocking {
        val t = transport(HttpResponse(200, """{"gated":true,"code":"opl_new","label":"phone ffff0000","expires_at":null}"""), opened)
        val (next, line) = claimPhoneCode(Settings(url, "", pairing), url, t)
        assertTrue(line.endsWith("(phone ffff0000)."))
        assertFalse(line.contains("until"))
        assertEquals("phone ffff0000", next.codeName)
    }

    @Test
    fun a_claim_whose_session_does_not_open_keeps_the_code_and_no_token() = runBlocking {
        val (next, line) = claimPhoneCode(Settings(url, "", pairing), url, transport(claimed, null))
        assertEquals("opl_new", next.accessCode)
        assertEquals("", next.token)
        assertTrue(line.contains("now has a code of its own"))
        val (refused, _) = claimPhoneCode(Settings(url, "", pairing), url, transport(claimed, HttpResponse(429, """{"detail":"too many tries; wait 9 s"}""")))
        assertEquals("", refused.token)
    }

    @Test
    fun an_ended_pairing_says_to_reload_the_page_and_scan_its_new_code() = runBlocking {
        val paired = Settings(url, "", pairing)
        val t = transport(HttpResponse(401, """{"detail":"the pairing has ended"}"""))
        val (left, line) = claimPhoneCode(paired, url, t)
        assertEquals(paired, left)
        assertTrue(line.endsWith("no code of its own: $CLAIM_ENDED."))
    }

    @Test
    fun only_a_current_pairing_without_a_code_of_its_own_is_claimed_again_at_start() {
        val now = 1_000L
        val held = "sid.${now + 60}.2.0.0123456789abcdef.${"a".repeat(32)}"
        assertTrue(shouldRetryClaim(Settings(url, "", held), now))
        assertTrue(shouldRetryClaim(Settings(url, "opl_typed", held), now))
        assertFalse(shouldRetryClaim(Settings(url, "", held), now + 60))
        assertFalse(shouldRetryClaim(Settings(url, "opl_mine", held, "phone abcd1234"), now))
        assertFalse(shouldRetryClaim(Settings(url, "", "sid.${now + 60}.1.0.0123456789abcdef.${"a".repeat(32)}"), now))
        assertFalse(shouldRetryClaim(Settings("", "", held), now))
    }
}
