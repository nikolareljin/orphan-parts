package com.orphanparts.lens.ui

import com.orphanparts.lens.Settings
import com.orphanparts.lens.api.FakeTransport
import com.orphanparts.lens.api.HttpResponse
import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UnpairTest {
    private val url = "https://demo.example"
    private val session = "sid.9999999999.1.0.0123456789abcdef.${"a".repeat(32)}"
    private val own = Settings(url, "opl_mine", session, "phone abcd1234", "2026-11-29T10:00:00+00:00")
    private val left = HttpResponse(200, """{"gated":true,"granted":false,"live":false}""")

    private fun transport(vararg answers: HttpResponse) = FakeTransport(ArrayDeque(answers.toList()))

    @Test
    fun the_backend_is_asked_to_forget_the_session_with_the_token_in_hand() = runBlocking {
        val t = transport(left)
        assertEquals(Settings("", ""), unpair(own, t))
        assertEquals(1, t.sent.size)
        assertEquals("DELETE", t.sent[0].method)
        assertEquals("$url/api/access", t.sent[0].url)
        assertEquals("Bearer $session", t.sent[0].headers["Authorization"])
        assertNull(t.sent[0].body)
    }

    @Test
    fun a_backend_that_does_not_answer_or_refuses_does_not_keep_the_phone_paired() = runBlocking {
        val down = object : FakeTransport(ArrayDeque()) {
            override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
                sent += Sent(method, url, headers, body)
                throw IOException("network is unreachable")
            }
        }
        assertEquals(Settings("", ""), unpair(own, down))
        assertEquals(1, down.sent.size)
        assertEquals(Settings("", ""), unpair(own, transport(HttpResponse(401, """{"detail":"that is not the access code"}"""))))
        assertEquals(Settings("", ""), unpair(own, transport(HttpResponse(503, ""))))
    }

    @Test
    fun without_a_session_nothing_is_sent_and_the_code_goes_all_the_same() = runBlocking {
        val t = transport()
        assertEquals(Settings("", ""), unpair(Settings(url, "typed"), t))
        assertEquals(Settings("", ""), unpair(Settings("", "", session), t))
        assertTrue(t.sent.isEmpty())
    }

    @Test
    fun the_question_names_the_phones_own_code_and_where_it_is_revoked() {
        val question = unpairQuestion(own)
        assertTrue(question.startsWith("Unpair this phone? It forgets the address, its code and its session."))
        assertTrue(question.endsWith("""./dev keys revoke "phone abcd1234""""))
        assertFalse(question.contains("opl_mine"))
        // a typed code, or a pairing alone, has nothing to revoke
        assertFalse(unpairQuestion(Settings(url, "typed", session)).contains("revoke"))
        assertFalse(unpairQuestion(Settings(url, "", session)).contains("revoke"))
    }
}
