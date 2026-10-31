package com.orphanparts.lens.ui

import com.orphanparts.lens.api.ApiException
import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.FakeTransport
import com.orphanparts.lens.api.HttpResponse
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.fail
import org.junit.Test

class SessionTest {
    private fun session(code: String, token: String, vararg answers: HttpResponse): Pair<Session, FakeTransport> {
        val transport = FakeTransport(ArrayDeque(answers.toList()))
        return Session(Client("http://backend:8000", transport), code, token) to transport
    }

    @Test
    fun the_pairing_session_goes_first_and_the_phones_own_code_opens_a_new_one_when_it_is_refused() = runBlocking {
        val (s, t) = session(
            "opl_mine",
            "paired.token",
            HttpResponse(401, """{"detail":"the session has ended"}"""),
            HttpResponse(200, """{"gated":true,"granted":true,"token":"fresh.token","expires_at":1}"""),
            HttpResponse(200, "[]"),
            HttpResponse(200, "[]"),
        )
        assertEquals(0, s.call { it.items() }.size)
        assertEquals("Bearer paired.token", t.sent[0].headers["Authorization"])
        assertEquals("http://backend:8000/api/access", t.sent[1].url)
        assertEquals("Bearer fresh.token", t.sent[2].headers["Authorization"])
        // the session opened with the code stays for the calls that follow
        s.call { it.items() }
        assertEquals("Bearer fresh.token", t.sent[3].headers["Authorization"])
    }

    @Test
    fun without_a_code_a_refused_pairing_says_to_scan_again() = runBlocking {
        val (s, t) = session("", "paired.token", HttpResponse(401, """{"detail":"the session has ended"}"""))
        try {
            s.call { it.items() }
            fail("expected the refusal")
        } catch (e: ApiException) {
            assertEquals(401, e.status)
            assertEquals("the pairing has ended; scan the code again", e.message)
        }
        assertEquals(1, t.sent.size)
    }

    @Test
    fun the_demo_visitor_has_no_door_and_sends_nothing_to_open_one() = runBlocking {
        val (s, t) = session("", "", HttpResponse(200, "[]"))
        assertEquals(false, s.hasDoor)
        s.call { it.items() }
        assertNull(t.sent[0].headers["Authorization"])
    }
}
