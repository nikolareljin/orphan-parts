import type { Capture, CaptureStatus } from './api'

export function statusLabel(status: CaptureStatus): string {
  switch (status) {
    case 'received':
      return 'received, not read yet'
    case 'processed':
      return 'read into an item'
    case 'failed':
      return 'could not be read'
  }
}

export function captureTone(status: CaptureStatus): 'fits' | 'conflict' | 'unsure' {
  if (status === 'processed') return 'fits'
  if (status === 'failed') return 'conflict'
  return 'unsure'
}

// What a capture holds, in one line.
export function captureSummary(c: Pick<Capture, 'photos' | 'clip' | 'clip_bytes' | 'audio' | 'audio_seconds' | 'name' | 'model'>): string {
  const parts: string[] = []
  parts.push(c.photos === 1 ? '1 photo' : `${c.photos} photos`)
  if (c.clip) parts.push(`a video of ${Math.max(1, Math.round(c.clip_bytes / 1024))} KB`)
  if (c.audio) parts.push(`a voice note of ${c.audio_seconds.toFixed(0)} s`)
  let text = parts.join(', ')
  if (c.name) text += ` · named ${c.name}`
  if (c.model) text += ` · read by ${c.model}`
  return text
}
