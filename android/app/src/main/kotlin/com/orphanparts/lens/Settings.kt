package com.orphanparts.lens

import android.content.Context

/** Where the backend is and the code that opens the demo; kept in the app's private storage. */
data class Settings(val baseUrl: String, val accessCode: String) {
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

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("orphan-parts", Context.MODE_PRIVATE)

    fun load(): Settings = Settings(
        baseUrl = prefs.getString("base_url", "") ?: "",
        accessCode = prefs.getString("access_code", "") ?: "",
    )

    fun save(settings: Settings) {
        prefs.edit()
            .putString("base_url", normalizeBaseUrl(settings.baseUrl))
            .putString("access_code", settings.accessCode.trim())
            .apply()
    }
}
