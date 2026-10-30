package com.orphanparts.lens.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Shapes
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldColors
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** The web app's look, on the phone: the same seven colors in light and dark
 * (frontend/src/index.css), panels with a hairline border, one scale of buttons, pills for
 * status, a quiet service line at the foot. Nothing here is a new library. */
object Tokens {
    data class Palette(
        val bg: Long,
        val fg: Long,
        val muted: Long,
        val card: Long,
        val line: Long,
        val accent: Long,
        val error: Long,
        val onAccent: Long,
    ) {
        /** The palette as the CSS custom properties it was taken from, for the test that keeps
         * the two in step. */
        fun asCss(): Map<String, String> = mapOf(
            "bg" to hex(bg), "fg" to hex(fg), "muted" to hex(muted), "card" to hex(card),
            "line" to hex(line), "accent" to hex(accent), "error" to hex(error),
            "on-accent" to hex(onAccent),
        )

        private fun hex(value: Long): String = "#%06x".format(value and 0xFFFFFF)
    }

    val light = Palette(
        bg = 0xFFF6F7F9, fg = 0xFF1B1F24, muted = 0xFF5B6470, card = 0xFFFFFFFF,
        line = 0xFFE2E6EB, accent = 0xFF2D6CDF, error = 0xFFB42318, onAccent = 0xFFFFFFFF,
    )
    val dark = Palette(
        bg = 0xFF0F1216, fg = 0xFFE6E9EE, muted = 0xFF9AA4B1, card = 0xFF171B21,
        line = 0xFF262C35, accent = 0xFF6EA0FF, error = 0xFFFF7A6B, onAccent = 0xFF0F1216,
    )

    fun palette(dark: Boolean): Palette = if (dark) this.dark else light
}

/** A status line that says something failed is shown in the error tone: every line the
 * screens write for a failure starts one of these ways. */
private val FAILURE_OPENINGS = listOf(
    "Could not", "Not reachable", "Nothing heard", "That code", "Scan canceled", "The photo could not",
    "The camera returned", "The clip is", "The clip could not", "The microphone was refused", "Capture #",
    "The code is refused", "The pairing has ended", "The pairing could not",
)

fun soundsLikeAFailure(text: String): Boolean = FAILURE_OPENINGS.any { text.startsWith(it) }

fun scheme(p: Tokens.Palette, dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    // as the web app: white on the light accent, the page color on the lighter dark one
    val onAccent = Color(p.onAccent)
    return base.copy(
        primary = Color(p.accent), onPrimary = onAccent,
        primaryContainer = Color(p.accent), onPrimaryContainer = onAccent,
        secondary = Color(p.muted), onSecondary = Color(p.card),
        background = Color(p.bg), onBackground = Color(p.fg),
        surface = Color(p.card), onSurface = Color(p.fg),
        surfaceVariant = Color(p.bg), onSurfaceVariant = Color(p.muted),
        surfaceContainer = Color(p.card), surfaceContainerLow = Color(p.card),
        surfaceContainerHigh = Color(p.card), surfaceContainerHighest = Color(p.bg),
        outline = Color(p.line), outlineVariant = Color(p.line),
        error = Color(p.error), onError = onAccent,
    )
}

private val LookShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(8.dp), // buttons and fields
    medium = RoundedCornerShape(10.dp), // panels
    large = RoundedCornerShape(12.dp), // the hold button, dialogs
    extraLarge = RoundedCornerShape(16.dp),
)

private val LookType = Typography().let {
    it.copy(
        titleLarge = TextStyle(fontSize = 21.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold),
        titleMedium = TextStyle(fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold),
        bodyMedium = it.bodyMedium.copy(fontSize = 15.sp, lineHeight = 21.sp),
        labelMedium = it.labelMedium.copy(fontSize = 12.sp, fontWeight = FontWeight.Medium),
    )
}

@Composable
fun OrphanPartsTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    MaterialTheme(
        colorScheme = scheme(Tokens.palette(dark), dark),
        shapes = LookShapes,
        typography = LookType,
        content = content,
    )
}

/** A card as the web app draws them: the card color, a hairline border, rounded corners. */
@Composable
fun Panel(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.medium,
        color = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), content = content)
    }
}

/** Filled with the accent: the one action of a form. */
@Composable
fun PrimaryButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Button(
        onClick = onClick,
        modifier = modifier,
        enabled = enabled,
        shape = MaterialTheme.shapes.small,
        colors = ButtonDefaults.buttonColors(
            containerColor = colors.primary,
            contentColor = colors.onPrimary,
            disabledContainerColor = colors.primary.copy(alpha = 0.55f),
            disabledContentColor = colors.onPrimary,
        ),
    ) { Text(text) }
}

/** Outlined in the accent on the card color: every other action. */
@Composable
fun SecondaryButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    OutlinedButton(
        onClick = onClick,
        modifier = modifier,
        enabled = enabled,
        shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, if (enabled) colors.primary else colors.outline),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = colors.surface,
            contentColor = colors.primary,
            disabledContainerColor = colors.surface,
            disabledContentColor = colors.onSurfaceVariant,
        ),
    ) { Text(text) }
}

/** Text fields with the line color at rest and the accent when focused. */
@Composable
fun fieldColors(): TextFieldColors {
    val colors = MaterialTheme.colorScheme
    return OutlinedTextFieldDefaults.colors(
        focusedBorderColor = colors.primary,
        unfocusedBorderColor = colors.outline,
        focusedLabelColor = colors.primary,
        unfocusedLabelColor = colors.onSurfaceVariant,
        focusedContainerColor = colors.surface,
        unfocusedContainerColor = colors.surface,
        focusedTextColor = colors.onSurface,
        unfocusedTextColor = colors.onSurface,
        cursorColor = colors.primary,
    )
}

enum class Tone { Quiet, Accent, Error }

/** A small bordered pill for a status word, as the web app's badges. */
@Composable
fun Pill(text: String, tone: Tone = Tone.Quiet) {
    val colors = MaterialTheme.colorScheme
    val color = when (tone) {
        Tone.Quiet -> colors.onSurfaceVariant
        Tone.Accent -> colors.primary
        Tone.Error -> colors.error
    }
    Text(
        text,
        color = color,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier
            .border(1.dp, if (tone == Tone.Quiet) colors.outline else color, RoundedCornerShape(999.dp))
            .padding(horizontal = 9.dp, vertical = 3.dp),
    )
}

/** What a screen last did, muted; in the error tone when it says something failed. */
@Composable
fun StatusLine(text: String) {
    if (text.isBlank()) return
    val colors = MaterialTheme.colorScheme
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium,
        color = if (soundsLikeAFailure(text)) colors.error else colors.onSurfaceVariant,
    )
}

/** Press and hold: `onStart` says whether to begin (and starts the recorder); `onStop` runs on
 * release, and when the gesture is cut short (the key changed under it). Every move of the
 * finger is consumed, so a scrolling page cannot take the hold away mid-sentence. Accent
 * while idle, the error tone while it listens, so recording is visible. */
@Composable
fun HoldButton(
    idle: String,
    active: String,
    modifier: Modifier = Modifier,
    key: Any? = Unit,
    onStart: () -> Boolean,
    onStop: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    var holding by remember { mutableStateOf(false) }
    Box(
        contentAlignment = Alignment.Center,
        modifier = modifier
            .fillMaxWidth()
            .height(64.dp)
            .background(if (holding) colors.error else colors.primary, MaterialTheme.shapes.large)
            .semantics(mergeDescendants = true) {
                role = Role.Button
                stateDescription = if (holding) "listening" else "ready"
            }
            .pointerInput(key) {
                awaitEachGesture {
                    awaitFirstDown().consume()
                    if (!onStart()) return@awaitEachGesture
                    holding = true
                    try {
                        do {
                            val event = awaitPointerEvent()
                            event.changes.forEach { it.consume() }
                        } while (event.changes.any { it.pressed })
                    } finally {
                        holding = false
                        onStop()
                    }
                }
            },
    ) {
        Text(
            if (holding) active else idle,
            color = colors.onPrimary,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
}

/** The quiet line at the foot of every screen: where the backend is and what answers. */
@Composable
fun ServiceLine(text: String) {
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
        HorizontalDivider(color = colors.outline)
        Spacer(Modifier.height(8.dp))
        Text(text, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
        Spacer(Modifier.height(10.dp))
    }
}

/** A small QR glyph drawn by hand (no icon library): the three finder squares and a few
 * modules. A tap opens the scanner to pair again from any page. */
@Composable
fun QrButton(onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Canvas(
        modifier = Modifier
            .size(48.dp) // the least touch target
            .border(1.dp, colors.outline, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .semantics {
                role = Role.Button
                contentDescription = "Scan to pair"
            }
            .padding(13.dp),
    ) {
        val m = size.width / 7f // seven modules across
        fun finder(x: Int, y: Int) {
            drawRect(colors.onBackground, Offset(x * m, y * m), Size(3 * m, 3 * m))
            drawRect(colors.background, Offset((x + 0.6f) * m, (y + 0.6f) * m), Size(1.8f * m, 1.8f * m))
            drawRect(colors.onBackground, Offset((x + 1) * m, (y + 1) * m), Size(m, m))
        }
        finder(0, 0)
        finder(4, 0)
        finder(0, 4)
        for ((x, y) in listOf(4 to 4, 6 to 4, 4 to 6, 5 to 5, 6 to 6)) {
            drawRect(colors.primary, Offset(x * m, y * m), Size(m, m))
        }
    }
}
