package com.orphanparts.lens

import android.content.Context
import org.json.JSONObject

/** Where the backend is and what opens it: the demo code, or a session the pairing gave;
 * kept in the app's private storage. */
data class Settings(val baseUrl: String, val accessCode: String, val token: String = "") {
    val ready: Boolean get() = baseUrl.isNotBlank()
}

/** A base URL as the client uses it: a scheme, no trailing slash, no path to the API. */
fun normalizeBaseUrl(text: String): String {
    var url = text.trim()
    if (url.isEmpty()) return ""
    if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://$url"
    url = url.trimEnd('/')
    if (url.endsWith("/api")) url = url.removeSuffix("/api")
    return url
}

/** The pairing payload a QR code carries: the origin, whether gated, a session token. The
 * code itself is kept as it was; a scan replaces the URL and the session, nothing else. */
/** On the phone, localhost is the phone: an address like that in a pairing code came from a
 * browser open on the computer itself and can never answer here. */
fun reachableFromAPhone(url: String): Boolean {
    val host = url.removePrefix("https://").removePrefix("http://").substringBefore('/').substringBefore(':').lowercase()
    return host.isNotEmpty() && host !in setOf("localhost", "127.0.0.1", "[", "0.0.0.0") && !host.endsWith(".localhost")
}

/** Whether a pairing code was refused only because it points at localhost. */
fun pointsAtLocalhost(text: String): Boolean {
    val url = try { normalizeBaseUrl(JSONObject(text).optString("url")) } catch (_: Exception) { return false }
    return url.isNotEmpty() && !reachableFromAPhone(url)
}

fun pairingFrom(text: String, current: Settings): Settings? {
    val json = try {
        JSONObject(text)
    } catch (_: Exception) {
        return null
    }
    // ours carries the origin and says whether the demo is gated; any other QR with a url is
    // somebody else's and not a pairing code
    if (!json.has("gated")) return null
    val url = normalizeBaseUrl(json.optString("url"))
    if (url.isEmpty() || !reachableFromAPhone(url)) return null
    return Settings(baseUrl = url, accessCode = current.accessCode, token = json.optString("token"))
}

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("orphan-parts", Context.MODE_PRIVATE)

    fun load(): Settings = Settings(
        baseUrl = prefs.getString("base_url", "") ?: "",
        accessCode = prefs.getString("access_code", "") ?: "",
        token = prefs.getString("token", "") ?: "",
    )

    fun save(settings: Settings) {
        prefs.edit()
            .putString("base_url", normalizeBaseUrl(settings.baseUrl))
            .putString("access_code", settings.accessCode.trim())
            .putString("token", settings.token.trim())
            .apply()
    }
}
