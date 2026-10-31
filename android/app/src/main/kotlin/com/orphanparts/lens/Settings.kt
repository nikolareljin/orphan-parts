package com.orphanparts.lens

import android.content.Context
import android.content.SharedPreferences
import com.orphanparts.lens.api.PhoneCode
import org.json.JSONObject
import java.net.InetAddress
import java.net.URI

/** Where the backend is and what opens it: a typed code, or the code of its own the phone
 * claimed with a pairing (its label and expiry say which code it holds; a typed code has
 * neither), and the token in hand: a pairing, or a session opened with the code. Kept in the
 * app's private storage. */
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

    /** The phone's own code by name: its label, and until when when that is known. */
    val codeName: String get() = if (codeExpiresDay.isBlank()) codeLabel else "$codeLabel, until $codeExpiresDay"
}

/** When a token ends, Unix seconds, read off its second field (`sid.expiry.door...`); null for
 * anything not shaped like one of ours. */
fun tokenExpiry(token: String): Long? = token.split('.').getOrNull(1)?.toLongOrNull()

/** Whether the token has ended by its own expiry (or is not one of ours): the backend serves an
 * ended token as the demo visitor without a word, so the phone must tell for itself. */
fun tokenEnded(token: String, nowSeconds: Long = System.currentTimeMillis() / 1000): Boolean {
    val exp = tokenExpiry(token) ?: return true
    return exp <= nowSeconds
}

/** Whether the token is a pairing (door 2), the short kind a QR carries that claims a code. */
fun isPairingToken(token: String): Boolean {
    val parts = token.split('.')
    return parts.size == 6 && parts[2] == "2"
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

/** The pairing payload a QR code carries: the origin, whether gated, a pairing token. For the
 * backend the phone already uses, the code it holds is kept and the scan replaces the token
 * (a gated code without one was shown to the demo visitor, and leaves the phone with its own
 * code if it has one). For any other backend the code, its label and expiry are dropped: a
 * code is never sent to another host. */
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
    val kept = if (url == current.baseUrl) current else Settings(baseUrl = url, accessCode = "")
    return kept.copy(baseUrl = url, token = json.optString("token"))
}

/** The settings once the phone has claimed its own code with the pairing: the code replaces
 * whatever was typed, and its label and expiry say so on the Backend tab. */
fun withPhoneCode(paired: Settings, own: PhoneCode): Settings =
    paired.copy(accessCode = own.code, codeLabel = own.label, codeExpires = own.expiresAt)

/** What Save on the Backend tab keeps of what is typed: the label and expiry stay with the
 * phone's own code only while both the address and the code are unchanged, and the token in
 * hand only while both are too (it belongs to that backend and that code). */
fun typedSettings(settings: Settings, url: String, code: String): Settings {
    val base = normalizeBaseUrl(url)
    val same = base == settings.baseUrl && code == settings.accessCode
    return Settings(
        base,
        code,
        token = if (same) settings.token else "",
        codeLabel = if (same) settings.codeLabel else "",
        codeExpires = if (same) settings.codeExpires else "",
    )
}

/** The claim's outcome applied to what is stored now, or null when the settings moved on while
 * it ran (another scan, a typed address): only the scan it started from takes it. */
fun applyClaim(current: Settings, scanned: Settings, claimed: Settings): Settings? =
    if (current.baseUrl == scanned.baseUrl && current.token == scanned.token) claimed else null

/** The settings once the phone's own code has ended (the backend refused it with 401), or null
 * when the store holds another code by then: the code, its label and the token go, so the
 * Backend tab shows a phone without a code instead of one that no longer opens. A live pairing
 * from a scan since stays (its claim running), so the claim still finds the scan it came from;
 * the pairing that claimed the ended code (its label is "phone " and the pairing's first eight
 * characters) is spent and goes with it. */
fun withoutEndedCode(current: Settings, code: String): Settings? =
    if (current.ownCode && current.accessCode == code) {
        val spent = current.codeLabel == "phone " + current.token.substringBefore('.').take(8)
        val live = isPairingToken(current.token) && !tokenEnded(current.token) && !spent
        val token = if (live) current.token else ""
        current.copy(accessCode = "", token = token, codeLabel = "", codeExpires = "")
    } else {
        null
    }

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("orphan-parts", Context.MODE_PRIVATE)

    fun load(): Settings = Settings(
        baseUrl = prefs.getString("base_url", "") ?: "",
        accessCode = prefs.getString("access_code", "") ?: "",
        token = prefs.getString("token", "") ?: "",
        codeLabel = prefs.getString("code_label", "") ?: "",
        codeExpires = prefs.getString("code_expires", "") ?: "",
    )

    /** Written in the background, or on disk before it returns when `durable` (a claimed code,
     * which the backend will not hand out again). */
    fun save(settings: Settings, durable: Boolean = false) {
        val edit = prefs.edit()
            .putString("base_url", normalizeBaseUrl(settings.baseUrl))
            .putString("access_code", settings.accessCode.trim())
            .putString("token", settings.token.trim())
            .putString("code_label", settings.codeLabel.trim())
            .putString("code_expires", settings.codeExpires.trim())
        if (durable) edit.commit() else edit.apply()
    }

    /** `onChange` on the main thread whenever the stored settings change, whoever wrote them;
     * the returned function stops it. The listener is held here: the preferences keep only a
     * weak reference to it. */
    fun observe(onChange: () -> Unit): () -> Unit {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> onChange() }
        prefs.registerOnSharedPreferenceChangeListener(listener)
        return { prefs.unregisterOnSharedPreferenceChangeListener(listener) }
    }
}
