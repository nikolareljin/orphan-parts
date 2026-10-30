package com.orphanparts.lens

/** What the backend accepts as a clip: an MP4 or 3GP file, told by its `ftyp` box and major
 * brand, never by its name. The same list the backend keeps, so a refusal is said here first. */
private val BRANDS = setOf(
    "isom", "iso2", "iso4", "iso5", "iso6", "mp41", "mp42", "avc1", "M4V ",
    "3gp4", "3gp5", "3gp6", "3gp7", "3ge6", "3gg6", "3gr6", "3gs6", "3g2a",
)

fun looksLikeVideo(bytes: ByteArray): Boolean =
    bytes.size > 12 && String(bytes, 4, 4, Charsets.ISO_8859_1) == "ftyp" &&
        String(bytes, 8, 4, Charsets.ISO_8859_1) in BRANDS
