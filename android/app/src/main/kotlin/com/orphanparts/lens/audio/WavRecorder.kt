package com.orphanparts.lens.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/** Hold to talk: 16 kHz mono 16-bit PCM from the microphone while the button is held, as a
 * WAV file when it is released. The permission is asked for by the screen before this starts. */
class WavRecorder(private val maxSeconds: Int = 60) {
    private val sampleRate = 16_000
    private val running = AtomicBoolean(false)
    private var thread: Thread? = null
    private val pcm = ByteArrayOutputStream()

    val isRecording: Boolean get() = running.get()

    /** Why the last start gave nothing: the microphone held by another app, or none at all. */
    @Volatile var problem: String? = null
        private set

    @SuppressLint("MissingPermission")
    fun start() {
        if (!running.compareAndSet(false, true)) return
        pcm.reset()
        problem = null
        val minBuffer = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(
            MediaRecorder.AudioSource.MIC, sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuffer, sampleRate),
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            // another app holds the microphone, or the device has none: nothing to record from
            record.release()
            problem = "the microphone is not available"
            running.set(false)
            return
        }
        val maxBytes = maxSeconds * sampleRate * 2
        thread = Thread {
            val buffer = ByteArray(4096)
            try {
                try {
                    record.startRecording()
                } catch (e: IllegalStateException) {
                    problem = "the microphone could not start"
                    running.set(false)
                }
                while (running.get() && pcm.size() < maxBytes) {
                    val n = record.read(buffer, 0, buffer.size)
                    if (n > 0) pcm.write(buffer, 0, n)
                }
            } finally {
                try {
                    record.stop()
                } catch (_: IllegalStateException) {
                    // never started
                }
                record.release()
            }
        }.also { it.start() }
    }

    /** Stops and returns the recording as a WAV file, or null when nothing was heard. */
    fun stop(): ByteArray? {
        if (!running.compareAndSet(true, false)) return null
        thread?.join(2_000)
        thread = null
        val bytes = pcm.toByteArray()
        return if (bytes.isEmpty()) null else wavFile(sampleRate, 1, 16, bytes)
    }

    fun seconds(): Double = wavSeconds(sampleRate, 1, 16, pcm.size())
}
