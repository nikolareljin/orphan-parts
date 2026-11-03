package com.orphanparts.lens.ui

import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.FakeTransport
import com.orphanparts.lens.api.HttpResponse
import com.orphanparts.lens.api.ItemView
import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The device question's state: shown while the backend asks, cleared by an answer, a refusal
 * said in the server's words, nothing for a phone without a code or a pairing. */
class DeviceQuestionTest {
    private val opened = HttpResponse(200, """{"gated":true,"granted":true,"token":"fresh.token","expires_at":1}""")
    private val asks = HttpResponse(200, """{"id":12,"version":3,"needs_parent":true,"fields":{}}""")
    private val answered = HttpResponse(200, """{"id":12,"version":4,"needs_parent":false,"fields":{"parent_device":{"value":"the drink mixer"}}}""")

    private fun session(vararg answers: HttpResponse): Pair<Session, FakeTransport> {
        val transport = FakeTransport(ArrayDeque(answers.toList()))
        return Session(Client("http://backend:8000", transport), "the code") to transport
    }

    private fun item(needs: Boolean, device: String = "", model: String = "", redacted: Boolean = false) =
        ItemView(12, "Agitator", 3, needs, device, model, redacted)

    @Test
    fun the_question_is_shown_while_the_backend_asks_and_cleared_by_the_owner_words() = runBlocking {
        val (s, t) = session(opened, asks, answered)
        val loaded = loadDevice(s, 12, DeviceAnswer())
        assertTrue(loaded.asks)
        assertTrue(loaded.shown(hasDoor = true))
        val saved = answerDevice(s, 12, loaded.copy(busy = true), "  the drink mixer ")
        assertFalse(saved.asks)
        assertFalse(saved.busy)
        assertEquals("", saved.error)
        assertEquals("the drink mixer", saved.cameFrom)
        // answered, the card still shows the Came from line
        assertTrue(saved.shown(hasDoor = true))
        assertEquals("the drink mixer", org.json.JSONObject(String(t.sent.last().body!!)).getString("value"))
    }

    @Test
    fun blank_words_send_nothing() = runBlocking {
        val (s, t) = session()
        val state = DeviceAnswer(item(true))
        assertEquals(state, answerDevice(s, 12, state, "   "))
        assertTrue(t.sent.isEmpty())
    }

    @Test
    fun a_photo_that_gives_a_model_answers_and_one_that_gives_none_still_asks() = runBlocking {
        val (s, _) = session(
            opened,
            HttpResponse(201, """{"item":{"id":12,"version":4,"needs_parent":false,"fields":{"parent_device_model":{"value":"Hamilton Beach 729"}}},"model":"Hamilton Beach 729"}"""),
            HttpResponse(201, """{"item":{"id":12,"version":5,"needs_parent":true,"fields":{}},"model":""}"""),
        )
        val read = photographDevice(s, 12, DeviceAnswer(item(true), busy = true), byteArrayOf(1))
        assertFalse(read.asks)
        assertEquals("Hamilton Beach 729", read.photoModel)
        assertEquals("Hamilton Beach 729", read.cameFrom)
        val none = photographDevice(s, 12, DeviceAnswer(item(true), busy = true), byteArrayOf(1))
        assertTrue(none.asks)
        assertEquals("", none.photoModel)
        assertFalse(none.busy)
    }

    @Test
    fun a_refusal_is_said_in_the_server_words_and_the_question_stays() = runBlocking {
        val (s, _) = session(
            opened,
            HttpResponse(409, """{"detail":"item 12 changed since version 3"}"""),
            HttpResponse(422, """{"detail":"an item keeps at most 4 photos of the device; this one has 4"}"""),
        )
        val before = DeviceAnswer(item(true), busy = true)
        val conflict = answerDevice(s, 12, before, "the drink mixer")
        assertEquals("item 12 changed since version 3 (HTTP 409)", conflict.error)
        assertTrue(conflict.asks)
        assertFalse(conflict.busy)
        val full = photographDevice(s, 12, before, byteArrayOf(1))
        assertEquals("an item keeps at most 4 photos of the device; this one has 4 (HTTP 422)", full.error)
        assertNull(full.photoModel)
    }

    @Test
    fun a_network_failure_is_said_and_a_failed_load_leaves_the_card_as_it_was() = runBlocking {
        val transport = object : FakeTransport(ArrayDeque(listOf(opened))) {
            var calls = 0
            override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
                calls += 1
                if (calls > 1) throw IOException("connection reset")
                return super.send(method, url, headers, body)
            }
        }
        val s = Session(Client("http://backend:8000", transport), "the code")
        val failed = answerDevice(s, 12, DeviceAnswer(item(true), busy = true), "the drink mixer")
        assertEquals("connection reset", failed.error)
        val kept = DeviceAnswer(item(true))
        assertEquals(kept, loadDevice(s, 12, kept))
    }

    @Test
    fun nothing_is_shown_without_a_door_or_for_the_visitor_or_when_nothing_is_asked() {
        assertFalse(DeviceAnswer(item(true)).shown(hasDoor = false))
        assertFalse(DeviceAnswer(item(true, redacted = true)).shown(hasDoor = true))
        assertFalse(DeviceAnswer(item(true, redacted = true)).asks)
        assertFalse(DeviceAnswer(item(false)).shown(hasDoor = true))
        assertFalse(DeviceAnswer().shown(hasDoor = true))
        assertEquals("Hamilton Beach 729, the drink mixer", DeviceAnswer(item(false, "the drink mixer", "Hamilton Beach 729")).cameFrom)
    }
}
