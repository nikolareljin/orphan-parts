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
fun pairingFrom(text: String, current: Settings): Settings? {
    val json = try {
        JSONObject(text)
    } catch (_: Exception) {
        return null
    }
    val url = normalizeBaseUrl(json.optString("url"))
    if (url.isEmpty()) return null
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
