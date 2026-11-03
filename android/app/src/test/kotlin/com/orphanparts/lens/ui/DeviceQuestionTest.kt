package com.orphanparts.lens.ui

import com.orphanparts.lens.api.Client
import com.orphanparts.lens.api.FakeTransport
import com.orphanparts.lens.api.HttpResponse
import com.orphanparts.lens.api.ItemView
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** The device question's state: shown while the backend asks, cleared by an answer, a refusal
 * said in the server's words, nothing for the demo visitor's view, each item read once. */
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
        assertTrue(loaded.shown)
        val saved = answerDevice(s, 12, loaded.copy(busy = true), "  the drink mixer ")
        assertFalse(saved.asks)
        assertFalse(saved.busy)
        assertEquals("", saved.error)
        assertEquals("the drink mixer", saved.cameFrom)
        // answered, the card still shows the Came from line
        assertTrue(saved.shown)
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
            HttpResponse(404, """{"detail":"item 12 not found"}"""),
            HttpResponse(422, """{"detail":"an item keeps at most 4 photos of the device; this one has 4"}"""),
        )
        val before = DeviceAnswer(item(true), busy = true)
        val gone = answerDevice(s, 12, before, "the drink mixer")
        assertEquals("item 12 not found (HTTP 404)", gone.error)
        assertFalse(gone.photoFailed)
        assertTrue(gone.asks)
        assertFalse(gone.busy)
        val full = photographDevice(s, 12, before, byteArrayOf(1))
        assertEquals("an item keeps at most 4 photos of the device; this one has 4 (HTTP 422)", full.error)
        assertTrue(full.photoFailed)
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
    fun nothing_is_shown_for_the_visitor_or_when_nothing_is_asked() {
        assertFalse(DeviceAnswer(item(true, redacted = true)).shown)
        assertFalse(DeviceAnswer(item(true, redacted = true)).asks)
        assertFalse(DeviceAnswer(item(false)).shown)
        assertFalse(DeviceAnswer().shown)
        assertEquals("Hamilton Beach 729, the drink mixer", DeviceAnswer(item(false, "the drink mixer", "Hamilton Beach 729")).cameFrom)
    }

    @Test
    fun an_ungated_backend_asks_a_phone_with_no_code_nor_pairing() = runBlocking {
        // no code, no token: every caller is the owner, and the item is served whole
        val transport = FakeTransport(ArrayDeque(listOf(asks)))
        val s = Session(Client("http://backend:8000", transport), "")
        assertFalse(s.hasDoor)
        val loaded = loadDevice(s, 12, DeviceAnswer())
        assertTrue(loaded.shown)
        assertTrue(loaded.asks)
        assertNull(transport.sent.single().headers["Authorization"])
    }

    @Test
    fun a_second_pick_while_a_photo_is_read_is_refused() {
        val started = DeviceAnswer(item(true), error = "earlier", photoFailed = true).startPhoto()!!
        assertTrue(started.busy)
        assertEquals("", started.error)
        assertFalse(started.photoFailed)
        assertNull(started.startPhoto())
    }

    @Test
    fun a_cancelled_call_is_not_taken_for_a_refusal() = runBlocking {
        val transport = object : FakeTransport(ArrayDeque(listOf(opened))) {
            override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
                if (url.endsWith("/api/access")) return super.send(method, url, headers, body)
                throw CancellationException("left the tab")
            }
        }
        val s = Session(Client("http://backend:8000", transport), "the code")
        for (call in listOf<suspend () -> Unit>(
            { loadDevice(s, 12, DeviceAnswer()) },
            { answerDevice(s, 12, DeviceAnswer(item(true)), "the drink mixer") },
            { photographDevice(s, 12, DeviceAnswer(item(true)), byteArrayOf(1)) },
        )) {
            try {
                call()
                fail("the cancellation goes on")
            } catch (_: CancellationException) {
                // rethrown
            }
        }
    }

    @Test
    fun each_item_is_read_once_for_the_session_until_cleared() = runBlocking {
        val (s, t) = session(opened, asks, HttpResponse(404, """{"detail":"item 13 not found"}"""), answered)
        val answers = DeviceAnswers(s)
        assertNull(answers.cached(12))
        assertTrue(answers.load(12).asks)
        // a second card, or the tab shown again, asks nothing
        assertTrue(answers.load(12).asks)
        assertTrue(answers.cached(12)!!.asks)
        // a failed read is kept too, so a private item is not asked again on every visit
        assertNull(answers.load(13).item)
        assertNull(answers.load(13).item)
        val gets = t.sent.filter { it.method == "GET" }.map { it.url }
        assertEquals(listOf("http://backend:8000/api/items/12", "http://backend:8000/api/items/13"), gets)
        // an answer given on the card is what the tab shows next time
        answers.put(12, DeviceAnswer(item(false, "the drink mixer")))
        assertFalse(answers.load(12).asks)
        answers.clear()
        assertFalse(answers.load(12).asks)
        assertEquals(3, t.sent.count { it.method == "GET" })
    }

    @Test
    fun at_most_two_items_are_read_at_once() = runBlocking {
        var inFlight = 0
        var most = 0
        val transport = object : FakeTransport(ArrayDeque()) {
            override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
                if (url.endsWith("/api/access")) return HttpResponse(200, """{"gated":false,"granted":true,"token":""}""")
                synchronized(this) { inFlight += 1; most = maxOf(most, inFlight) }
                Thread.sleep(50)
                synchronized(this) { inFlight -= 1 }
                val id = url.substringAfterLast('/')
                return HttpResponse(200, """{"id":$id,"version":1,"needs_parent":true,"fields":{}}""")
            }
        }
        val answers = DeviceAnswers(Session(Client("http://backend:8000", transport), "the code"))
        (1..6).map { id -> async { answers.load(id) } }.awaitAll()
        assertTrue("at most ${DeviceAnswers.LOADS_AT_ONCE} reads at once, saw $most", most <= DeviceAnswers.LOADS_AT_ONCE)
        assertTrue((1..6).all { answers.cached(it)!!.asks })
    }
}
