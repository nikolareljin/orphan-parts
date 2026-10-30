package com.orphanparts.lens.audio

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** The 44-byte header of a PCM WAV file, which is what the backend takes for a voice note. */
fun wavHeader(sampleRate: Int, channels: Int, bitsPerSample: Int, dataBytes: Int): ByteArray {
    val byteRate = sampleRate * channels * bitsPerSample / 8
    val blockAlign = channels * bitsPerSample / 8
    val buffer = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
    buffer.put("RIFF".toByteArray(Charsets.US_ASCII))
    buffer.putInt(36 + dataBytes)
    buffer.put("WAVE".toByteArray(Charsets.US_ASCII))
    buffer.put("fmt ".toByteArray(Charsets.US_ASCII))
    buffer.putInt(16)
    buffer.putShort(1)
    buffer.putShort(channels.toShort())
    buffer.putInt(sampleRate)
    buffer.putInt(byteRate)
    buffer.putShort(blockAlign.toShort())
    buffer.putShort(bitsPerSample.toShort())
    buffer.put("data".toByteArray(Charsets.US_ASCII))
    buffer.putInt(dataBytes)
    return buffer.array()
}

/** A WAV file from raw little-endian PCM samples. */
fun wavFile(sampleRate: Int, channels: Int, bitsPerSample: Int, pcm: ByteArray): ByteArray {
    val out = ByteArrayOutputStream(44 + pcm.size)
    out.write(wavHeader(sampleRate, channels, bitsPerSample, pcm.size))
    out.write(pcm)
    return out.toByteArray()
}

/** How long a recording is, from its size. */
fun wavSeconds(sampleRate: Int, channels: Int, bitsPerSample: Int, pcmBytes: Int): Double =
    pcmBytes.toDouble() / (sampleRate * channels * bitsPerSample / 8)
