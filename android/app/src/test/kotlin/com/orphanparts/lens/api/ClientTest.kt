package com.orphanparts.lens.api

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** A transport that records what was sent and answers from a script. */
class FakeTransport(private val answers: ArrayDeque<HttpResponse>) : Transport {
    data class Sent(val method: String, val url: String, val headers: Map<String, String>, val body: ByteArray?)

    val sent = mutableListOf<Sent>()

    override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpResponse {
        sent += Sent(method, url, headers, body)
        return answers.removeFirst()
    }
}

class ClientTest {
    private fun client(vararg answers: HttpResponse): Pair<Client, FakeTransport> {
        val transport = FakeTransport(ArrayDeque(answers.toList()))
        return Client("http://backend:8000", transport) to transport
    }

    @Test
    fun readiness_reads_the_gate_off_the_demo_block() {
        val (c, t) = client(HttpResponse(200, """{"status":"ok","model_api":"fixture","demo":{"gated":true}}"""))
        val ready = c.readiness()
        assertEquals("ok", ready.status)
        assertEquals("fixture", ready.modelApi)
        assertTrue(ready.gated)
        assertEquals("GET", t.sent[0].method)
        assertEquals("http://backend:8000/readyz", t.sent[0].url)
        assertNull(t.sent[0].headers["Authorization"])
    }

    @Test
    fun access_keeps_the_token_for_the_calls_that_follow() {
        val (c, t) = client(
            HttpResponse(200, """{"gated":true,"granted":true,"token":"abc.def.ghi","expires_at":1}"""),
            HttpResponse(200, "[]"),
        )
        assertTrue(c.access("the demo code"))
        c.items()
        val opened = t.sent[0]
        assertEquals("POST", opened.method)
        assertEquals("http://backend:8000/api/access", opened.url)
        assertEquals("application/json", opened.headers["Content-Type"])
        assertEquals("the demo code", JSONObject(String(opened.body!!)).getString("code"))
        assertEquals("Bearer abc.def.ghi", t.sent[1].headers["Authorization"])
    }

    @Test
    fun extract_sends_the_photo_as_multipart_and_reads_the_fields() {
        val (c, t) = client(
            HttpResponse(
                200,
                """{"item_type":"power adapter","label_text":"19.5V","fields":{"output_voltage":{"value":"19.5","unit":"V","confidence":0.9,"source":"photo","raw":"19.5V"},"brand":{"value":"Orbital","unit":"","confidence":0.8,"source":"photo","raw":"Orbital"}},"warnings":["one warning"],"photos":1,"crops":0,"model":"muse-spark-1.3","from_fixture":true,"cost_usd":0.0}""",
            ),
        )
        val read = c.extract(byteArrayOf(1, 2, 3))
        assertEquals("power adapter", read.itemType)
        assertEquals(listOf("brand", "output_voltage"), read.fields.map { it.name })
        assertEquals("V", read.fields[1].unit)
        assertEquals(listOf("one warning"), read.warnings)
        assertTrue(read.fromFixture)
        val sent = t.sent[0]
        assertEquals("http://backend:8000/api/extract", sent.url)
        assertTrue(sent.headers["Content-Type"]!!.startsWith("multipart/form-data; boundary="))
        val body = String(sent.body!!, Charsets.ISO_8859_1)
        assertTrue(body.contains("name=\"photos\"; filename=\"capture.jpg\""))
        assertTrue(body.contains("Content-Type: image/jpeg"))
    }

    @Test
    fun save_item_carries_the_whole_reading_and_the_owner_words() {
        val reading = Client.parseExtraction(JSONObject("""{"item_type":"laptop","fields":{},"warnings":[]}"""))
        val (c, t) = client(HttpResponse(201, """{"id":7,"name":"Old laptop","item_type":"laptop","version":1}"""))
        val saved = c.saveItem(reading, "Old laptop", "boots, battery weak")
        assertEquals(7, saved.id)
        val body = JSONObject(String(t.sent[0].body!!))
        assertEquals("laptop", body.getJSONObject("extraction").getString("item_type"))
        assertEquals("Old laptop", body.getString("name"))
        assertEquals("boots, battery weak", body.getString("condition"))
    }

    @Test
    fun voice_note_uploads_a_wav_and_reads_the_transcript() {
        val (c, t) = client(HttpResponse(200, """{"transcript":"the fan is loud","seconds":2.5,"cut":false,"model":"muse-voice-transcribe-1.0","from_fixture":true,"cost_usd":0.0,"item":{}}"""))
        val note = c.voiceNote(7, byteArrayOf(82, 73, 70, 70))
        assertEquals("the fan is loud", note.transcript)
        assertEquals(2.5, note.seconds, 0.0)
        assertFalse(note.cut)
        assertEquals("http://backend:8000/api/items/7/voice", t.sent[0].url)
        assertTrue(String(t.sent[0].body!!, Charsets.ISO_8859_1).contains("name=\"audio\"; filename=\"note.wav\""))
    }

    @Test
    fun an_error_answer_is_the_backend_detail_and_its_status() {
        val (c, _) = client(HttpResponse(422, """{"detail":[{"loc":["body","name"],"msg":"name must not be blank"}]}"""))
        try {
            c.items()
            fail("expected an error")
        } catch (e: ApiException) {
            assertEquals(422, e.status)
            assertEquals("name must not be blank", e.message)
        }
        assertEquals("the code is wrong", Client.detailOf(HttpResponse(401, """{"detail":"the code is wrong"}""")))
        assertEquals("HTTP 502", Client.detailOf(HttpResponse(502, "bad gateway")))
    }
}
