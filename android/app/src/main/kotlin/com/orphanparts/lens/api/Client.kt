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
