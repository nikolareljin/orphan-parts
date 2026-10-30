package com.orphanparts.lens

import com.orphanparts.lens.ui.Tokens
import com.orphanparts.lens.ui.soundsLikeAFailure
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class LookTest {
    private fun cssTokens(block: String): Map<String, String> =
        Regex("""--([a-z]+):\s*(#[0-9a-fA-F]{6});""").findAll(block)
            .associate { it.groupValues[1] to it.groupValues[2].lowercase() }

    @Test
    fun the_palette_is_the_web_apps_in_light_and_dark() {
        // the unit tests run from android/app; the web app's tokens are two directories up
        val css = File("../../frontend/src/index.css")
        assertTrue("the web app's stylesheet is next to the app: ${css.absolutePath}", css.isFile)
        val text = css.readText()
        val dark = text.indexOf("prefers-color-scheme: dark")
        assertTrue(dark > 0)
        assertEquals(cssTokens(text.substring(0, dark)), Tokens.light.asCss())
        assertEquals(cssTokens(text.substring(dark)), Tokens.dark.asCss())
    }

    @Test
    fun the_palette_names_every_token_once() {
        assertEquals(setOf("bg", "fg", "muted", "card", "line", "accent", "error"), Tokens.light.asCss().keys)
        assertEquals(Tokens.light, Tokens.palette(dark = false))
        assertEquals(Tokens.dark, Tokens.palette(dark = true))
    }

    @Test
    fun a_status_that_says_it_failed_reads_as_one() {
        assertTrue(soundsLikeAFailure("Could not send: timeout"))
        assertTrue(soundsLikeAFailure("Not reachable: refused"))
        assertTrue(soundsLikeAFailure("Nothing heard."))
        assertFalse(soundsLikeAFailure("Sent as capture #3: 2 photo(s). See Captures."))
        assertFalse(soundsLikeAFailure(""))
    }
}
