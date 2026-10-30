import { describe, expect, it } from 'vitest'
import { captureSummary, captureTone, statusLabel } from './captures'

describe('captures', () => {
  it('names every status and its tone', () => {
    expect(statusLabel('received')).toBe('received, not read yet')
    expect(statusLabel('processed')).toBe('read into an item')
    expect(statusLabel('failed')).toBe('could not be read')
    expect(captureTone('processed')).toBe('fits')
    expect(captureTone('failed')).toBe('conflict')
    expect(captureTone('received')).toBe('unsure')
  })
  it('sums up what a capture holds', () => {
    expect(captureSummary({ photos: 1, clip: false, clip_bytes: 0, audio: false, audio_seconds: 0, name: '', model: '' })).toBe('1 photo')
    expect(
      captureSummary({ photos: 2, clip: true, clip_bytes: 3 * 1024, audio: true, audio_seconds: 2.4, name: 'Old adapter', model: 'muse-spark-1.3' }),
    ).toBe('2 photos, a clip of 3 KB, a note of 2 s · named Old adapter · read by muse-spark-1.3')
    expect(captureSummary({ photos: 0, clip: true, clip_bytes: 10, audio: false, audio_seconds: 0, name: '', model: '' })).toBe('0 photos, a clip of 1 KB')
  })
})
