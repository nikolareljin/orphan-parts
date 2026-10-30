package com.orphanparts.lens.api

import org.json.JSONArray
import org.json.JSONObject

/** One value read off a label, as the backend reports it. */
data class Field(val name: String, val value: String, val unit: String, val confidence: Double, val source: String)

/** A reading of a photo: the typed fields, the kind of item, the warnings. */
data class Extraction(
    val itemType: String,
    val labelText: String,
    val fields: List<Field>,
    val warnings: List<String>,
    val model: String,
    val fromFixture: Boolean,
    val raw: JSONObject,
)

data class SavedItem(val id: Int, val name: String, val itemType: String, val version: Int)

data class ItemLine(val id: Int, val name: String, val itemType: String, val availability: String)

data class VoiceNote(val transcript: String, val seconds: Double, val cut: Boolean, val model: String)

data class Readiness(val status: String, val modelApi: String, val gated: Boolean)

/** One bundle sent from the phone, and where the backend stands with it. */
data class Capture(
    val id: Int,
    val status: String,
    val note: String,
    val name: String,
    val photos: Int,
    val clip: Boolean,
    val audio: Boolean,
    val audioSeconds: Double,
    val itemId: Int?,
    val error: String,
    val model: String,
    val createdAt: String,
)

class ApiException(val status: Int, message: String) : Exception(message)

/** The backend, by the paths the web app uses; the session token from the access code goes
 * with every call as a bearer header, since the phone keeps no cookies. */
class Client(private val baseUrl: String, private val transport: Transport, private var token: String = "") {

    fun readiness(): Readiness {
        val json = get("/readyz")
        val demo = json.optJSONObject("demo")
        return Readiness(
            status = json.optString("status"),
            modelApi = json.optString("model_api"),
            gated = demo?.optBoolean("gated") ?: false,
        )
    }

    /** Opens a session with the demo access code; the token is kept for the calls that follow.
     * Without a gate the backend answers granted with an empty token. */
    fun access(code: String): Boolean {
        val json = send("POST", "/api/access", JSONObject().put("code", code).toString().toByteArray(), "application/json")
        token = json.optString("token", "")
        return json.optBoolean("granted", false)
    }

    fun extract(jpeg: ByteArray): Extraction {
        val body = Multipart().file("photos", "capture.jpg", "image/jpeg", jpeg)
        val json = send("POST", "/api/extract", body.bytes(), body.contentType)
        return parseExtraction(json)
    }

    fun saveItem(extraction: Extraction, name: String, condition: String): SavedItem {
        val spec = JSONObject()
            .put("extraction", extraction.raw)
            .put("name", name)
            .put("item_type", extraction.itemType)
            .put("condition", condition)
        val json = send("POST", "/api/items", spec.toString().toByteArray(), "application/json")
        return SavedItem(json.getInt("id"), json.optString("name"), json.optString("item_type"), json.optInt("version"))
    }

    fun items(): List<ItemLine> {
        val array = getArray("/api/items")
        return (0 until array.length()).map { i ->
            val o = array.getJSONObject(i)
            ItemLine(o.getInt("id"), o.optString("name"), o.optString("item_type"), o.optString("availability"))
        }
    }

    fun voiceNote(itemId: Int, wav: ByteArray): VoiceNote {
        val body = Multipart().file("audio", "note.wav", "audio/wav", wav)
        val json = send("POST", "/api/items/$itemId/voice", body.bytes(), body.contentType)
        return VoiceNote(json.optString("transcript"), json.optDouble("seconds", 0.0), json.optBoolean("cut"), json.optString("model"))
    }

    /** The capture bundle: every photo under `photos`, the clip, the note and the text part. */
    fun sendCapture(photos: List<ByteArray>, clip: ByteArray?, audio: ByteArray?, name: String, note: String): Capture {
        val body = Multipart()
        for ((n, photo) in photos.withIndex()) body.file("photos", "photo-${n + 1}.jpg", "image/jpeg", photo)
        if (clip != null) body.file("clip", "clip.mp4", "video/mp4", clip)
        if (audio != null) body.file("audio", "note.wav", "audio/wav", audio)
        body.text("request", JSONObject().put("name", name).put("note", note).put("find_label", true).toString())
        // streamed: the clip goes to the connection as it is, never copied into a second buffer
        return parseCapture(JSONObject(check(transport.send("POST", baseUrl + "/api/captures", headers(body.contentType), body))))
    }

    fun captures(): List<Capture> {
        val array = get("/api/captures").optJSONArray("captures") ?: JSONArray()
        return (0 until array.length()).map { parseCapture(array.getJSONObject(it)) }
    }

    fun processCapture(id: Int): Capture =
        parseCapture(send("POST", "/api/captures/$id/process", ByteArray(0), "application/json"))

    private fun headers(contentType: String?): Map<String, String> {
        val h = mutableMapOf<String, String>()
        if (contentType != null) h["Content-Type"] = contentType
        if (token.isNotEmpty()) h["Authorization"] = "Bearer $token"
        return h
    }

    private fun get(path: String): JSONObject = JSONObject(check(transport.send("GET", baseUrl + path, headers(null), null)))

    private fun getArray(path: String): JSONArray = JSONArray(check(transport.send("GET", baseUrl + path, headers(null), null)))

    private fun send(method: String, path: String, body: ByteArray, contentType: String): JSONObject =
        JSONObject(check(transport.send(method, baseUrl + path, headers(contentType), body)))

    private fun check(response: HttpResponse): String {
        if (response.ok) return response.body
        throw ApiException(response.status, detailOf(response))
    }

    companion object {
        /** The backend's error text is written to be shown; a 422 lists one problem per line. */
        fun detailOf(response: HttpResponse): String {
            try {
                val json = JSONObject(response.body)
                val detail = json.opt("detail")
                if (detail is String) return detail
                if (detail is JSONArray) {
                    val messages = (0 until detail.length()).mapNotNull { detail.optJSONObject(it)?.optString("msg") }
                    if (messages.isNotEmpty()) return messages.joinToString("; ")
                }
            } catch (_: Exception) {
                // not JSON
            }
            return "HTTP ${response.status}"
        }

        fun parseCapture(json: JSONObject): Capture = Capture(
            id = json.getInt("id"),
            status = json.optString("status"),
            note = json.optString("note"),
            name = json.optString("name"),
            photos = json.optInt("photos"),
            clip = json.optBoolean("clip"),
            audio = json.optBoolean("audio"),
            audioSeconds = json.optDouble("audio_seconds", 0.0),
            itemId = if (json.isNull("item_id")) null else json.optInt("item_id"),
            error = json.optString("error"),
            model = json.optString("model"),
            createdAt = json.optString("created_at"),
        )

        fun parseExtraction(json: JSONObject): Extraction {
            val fields = json.optJSONObject("fields") ?: JSONObject()
            val list = fields.keys().asSequence().map { key ->
                val f = fields.getJSONObject(key)
                Field(key, f.optString("value"), f.optString("unit"), f.optDouble("confidence", 0.0), f.optString("source"))
            }.sortedBy { it.name }.toList()
            val warnings = json.optJSONArray("warnings") ?: JSONArray()
            return Extraction(
                itemType = json.optString("item_type"),
                labelText = json.optString("label_text"),
                fields = list,
                warnings = (0 until warnings.length()).map { warnings.getString(it) },
                model = json.optString("model"),
                fromFixture = json.optBoolean("from_fixture"),
                raw = json,
            )
        }
    }
}
