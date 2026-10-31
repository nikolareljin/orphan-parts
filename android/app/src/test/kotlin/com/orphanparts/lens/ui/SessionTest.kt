package com.orphanparts.lens.ui

import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.FakeTransport
import com.orphanparts.lens.api.HttpResponse
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** The backend's real answers: an ended or revoked session is the demo visitor, so a write is
 * refused with 403 and the demo line, and an expired token is told by its own expiry field. */
class SessionTest {
    private val now = 1_000_000L
    private val current = "sid.${now + 600}.1.0.0123456789abcdef.${"a".repeat(32)}"
    private val expired = "sid.${now - 1}.1.0.0123456789abcdef.${"a".repeat(32)}"
    private val demoRefusal = HttpResponse(403, """{"detail":"demo: the code unlocks saving, drafts, prices, projects and captures"}""")
    private val opened = HttpResponse(200, """{"gated":true,"granted":true,"token":"fresh.token","expires_at":1}""")
    private val granted = HttpResponse(200, """{"gated":true,"granted":true,"live":true}""")
    private val notGranted = HttpResponse(200, """{"gated":true,"granted":false,"live":false}""")
    private val ownEnded = HttpResponse(401, """{"detail":"that is not the access code"}""")

    private var ended = 0

    private fun session(code: String, token: String, own: Boolean, vararg answers: HttpResponse): Pair<Session, FakeTransport> {
        val transport = FakeTransport(ArrayDeque(answers.toList()))
        return Session(Client("http://backend:8000", transport), code, token, own, { now }, { ended += 1 }) to transport
    }

    private fun FakeTransport.accessPosts() = sent.count { it.method == "POST" && it.url.endsWith("/api/access") }

    private fun save(c: Client) = c.processCapture(1)

    @Test
    fun a_demo_refusal_of_the_token_in_hand_opens_a_session_with_the_phones_code() = runBlocking {
        val (s, t) = session(
            "opl_mine",
            current,
            true,
            granted,
            demoRefusal,
            opened,
            HttpResponse(200, """{"id":1,"status":"done"}"""),
            HttpResponse(200, """{"id":1,"status":"done"}"""),
        )
        assertEquals(1, s.call { save(it) }.id)
        assertEquals("GET", t.sent[0].method)
        assertEquals("Bearer $current", t.sent[1].headers["Authorization"])
        assertEquals("http://backend:8000/api/access", t.sent[2].url)
        assertEquals("Bearer fresh.token", t.sent[3].headers["Authorization"])
        // the session opened with the code stays for the calls that follow
        s.call { save(it) }
        assertEquals("Bearer fresh.token", t.sent[4].headers["Authorization"])
    }

    @Test
    fun an_expired_token_is_not_sent_the_code_opens_a_session_first() = runBlocking {
        val (s, t) = session("opl_mine", expired, true, opened, HttpResponse(200, "[]"))
        s.call { it.items() }
        assertEquals("http://backend:8000/api/access", t.sent[0].url)
        assertEquals("Bearer fresh.token", t.sent[1].headers["Authorization"])
    }

    @Test
    fun a_refused_own_code_says_it_has_ended() = runBlocking {
        val (s, _) = session("opl_mine", expired, true, ownEnded)
        try {
            s.call { it.items() }
            fail("expected the refusal")
        } catch (e: ApiException) {
            assertEquals(401, e.status)
            assertEquals(OWN_CODE_ENDED, e.message)
        }
    }

    @Test
    fun without_a_code_an_ended_pairing_says_to_scan_again() = runBlocking {
        // still within its time, but refused (revoked): the demo line on a write
        val (s, t) = session("", current, false, granted, demoRefusal)
        try {
            s.call { save(it) }
            fail("expected the refusal")
        } catch (e: ApiException) {
            assertEquals(403, e.status)
            assertEquals(PAIRING_ENDED, e.message)
        }
        assertEquals(2, t.sent.size)
        // past its time it is not sent at all, and the phone has no door
        val (late, sent) = session("", expired, false, HttpResponse(200, "[]"))
        assertFalse(late.hasDoor)
        late.call { it.items() }
        assertNull(sent.sent[0].headers["Authorization"])
    }

    @Test
    fun the_demo_visitor_has_no_door_and_its_refusals_stand() = runBlocking {
        val (s, t) = session("", "", false, HttpResponse(200, "[]"), demoRefusal)
        assertEquals(false, s.hasDoor)
        s.call { it.items() }
        assertNull(t.sent[0].headers["Authorization"])
        try {
            s.call { save(it) }
            fail("expected the refusal")
        } catch (e: ApiException) {
            assertTrue(e.message!!.startsWith(DEMO_REFUSAL))
        }
    }

    @Test
    fun an_ended_own_code_is_sent_once_and_its_refusal_stays() = runBlocking {
        val (s, t) = session("opl_mine", expired, true, ownEnded)
        repeat(2) {
            try {
                s.call { it.items() }
                fail("expected the refusal")
            } catch (e: ApiException) {
                assertEquals(OWN_CODE_ENDED, e.message)
            }
        }
        assertEquals(1, t.accessPosts())
        assertEquals(1, t.sent.size)
        assertEquals(1, ended)
    }

    @Test
    fun a_held_token_the_backend_no_longer_grants_gives_way_to_the_code() = runBlocking {
        val (s, t) = session("opl_mine", current, true, notGranted, opened, HttpResponse(200, "[]"))
        s.call { it.items() }
        assertEquals("GET", t.sent[0].method)
        assertEquals("http://backend:8000/api/access", t.sent[0].url)
        assertEquals("Bearer $current", t.sent[0].headers["Authorization"])
        assertEquals(1, t.accessPosts())
        assertEquals("Bearer fresh.token", t.sent[2].headers["Authorization"])
    }

    @Test
    fun a_refusal_that_is_not_the_demo_line_does_not_open_again() = runBlocking {
        val browser = HttpResponse(403, """{"detail":"a browser's session does not claim a phone's code; scan the QR code with the app"}""")
        val (s, t) = session("opl_mine", current, true, granted, browser)
        try {
            s.call { save(it) }
            fail("expected the refusal")
        } catch (e: ApiException) {
            assertEquals(403, e.status)
            assertTrue(e.message!!.startsWith("a browser's session"))
        }
        assertEquals(0, t.accessPosts())
        assertEquals(2, t.sent.size)
    }

    @Test
    fun a_session_is_opened_again_once_a_second_demo_refusal_stands() = runBlocking {
        val (s, t) = session("opl_mine", current, true, granted, demoRefusal, opened, demoRefusal)
        try {
            s.call { save(it) }
            fail("expected the refusal")
        } catch (e: ApiException) {
            assertTrue(e.message!!.startsWith(DEMO_REFUSAL))
        }
        assertEquals(1, t.accessPosts())
        assertEquals(4, t.sent.size)
    }
}
