package com.orphanparts.lens

import android.content.Context
import com.orphanparts.lens.api.PhoneCode
import org.json.JSONObject
import java.net.InetAddress
import java.net.URI

/** Where the backend is and what opens it: the demo code, or a session the pairing gave and
 * the code of its own the phone claimed with it (its label and expiry say which code it
 * holds; a typed code has neither); kept in the app's private storage. */
data class Settings(
    val baseUrl: String,
    val accessCode: String,
    val token: String = "",
    val codeLabel: String = "",
    val codeExpires: String = "",
) {
    val ready: Boolean get() = baseUrl.isNotBlank()

    /** Whether the code held is one the backend issued to this phone on a scan. */
    val ownCode: Boolean get() = accessCode.isNotBlank() && codeLabel.isNotBlank()

    /** The code's expiry as a day. */
    val codeExpiresDay: String get() = codeExpires.take(10)
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

/** On the phone, localhost is the phone: an address like that in a pairing code came from a
 * browser open on the computer itself and can never answer here. The whole loopback range
 * (127.x.x.x, ::1), the unspecified address and the .localhost names are that; any other
 * host, a bracketed IPv6 address included, may be reachable. */
fun reachableFromAPhone(url: String): Boolean {
    val parsed = try { URI(url) } catch (_: Exception) { return false }
    // a name the URI class will not call a host (an underscore in it) is still a host
    val host = (parsed.host ?: parsed.authority?.substringBefore(':'))?.lowercase() ?: return false
    if (host.isEmpty() || host == "localhost" || host.endsWith(".localhost")) return false
    // an address literal (a dotted quad, or IPv6 in brackets in any spelling): the address itself
    // says whether it is loopback or unspecified. Anything else is a name, and a name is never
    // resolved here: the Check on the Backend tab says whether it answers
    val literal = host.startsWith("[") || Regex("""\d{1,3}(\.\d{1,3}){3}""").matches(host)
    if (literal) {
        val address = try { InetAddress.getByName(host.trim('[', ']')) } catch (_: Exception) { return false }
        return !address.isLoopbackAddress && !address.isAnyLocalAddress
    }
    return true
}

/** Whether a pairing code (one of ours: it says `gated`) was refused only because it points
 * at localhost. */
fun pointsAtLocalhost(text: String): Boolean {
    val json = try { JSONObject(text) } catch (_: Exception) { return false }
    if (!json.has("gated")) return false
    val url = normalizeBaseUrl(json.optString("url"))
    return url.isNotEmpty() && !reachableFromAPhone(url)
}

/** The pairing payload a QR code carries: the origin, whether gated, a session token. The
 * code itself is kept as it was; a scan replaces the URL and the session, nothing else. A
 * gated pairing without a session was shown to the demo visitor: the phone joins as the
 * demo too, with the address alone and no code, until a scan of a signed-in page. */
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
    val token = json.optString("token")
    if (json.optBoolean("gated") && token.isEmpty()) return Settings(baseUrl = url, accessCode = "")
    return current.copy(baseUrl = url, token = token)
}

/** The settings once the phone has claimed its own code with the pairing's session: the
 * code replaces whatever was typed, and its label and expiry say so on the Backend tab. */
fun withPhoneCode(paired: Settings, own: PhoneCode): Settings =
    paired.copy(accessCode = own.code, codeLabel = own.label, codeExpires = own.expiresAt)

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("orphan-parts", Context.MODE_PRIVATE)

    fun load(): Settings = Settings(
        baseUrl = prefs.getString("base_url", "") ?: "",
        accessCode = prefs.getString("access_code", "") ?: "",
        token = prefs.getString("token", "") ?: "",
        codeLabel = prefs.getString("code_label", "") ?: "",
        codeExpires = prefs.getString("code_expires", "") ?: "",
    )

    fun save(settings: Settings) {
        prefs.edit()
            .putString("base_url", normalizeBaseUrl(settings.baseUrl))
            .putString("access_code", settings.accessCode.trim())
            .putString("token", settings.token.trim())
            .putString("code_label", settings.codeLabel.trim())
            .putString("code_expires", settings.codeExpires.trim())
            .apply()
    }
}
