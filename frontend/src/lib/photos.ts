import type { Limits } from './api'

// Used until /api/version has answered; the backend defaults are the same.
export const DEFAULT_LIMITS: Limits = { max_photos: 4, max_upload_mb: 12, max_clip_mb: 60 }

export function takePhotos(files: File[], max: number): { kept: File[]; dropped: number } {
  const kept = files.slice(0, Math.max(max, 0))
  return { kept, dropped: files.length - kept.length }
}

// What is wrong with a clip before it is sent, or null: the size against the limit, and the
// container by its name when the browser gives one (the backend reads the bytes).
export function clipProblem(file: File, maxMb: number): string | null {
  if (file.size === 0) return `${file.name} is empty`
  if (file.size > maxMb * 1024 * 1024) return `${file.name} is ${(file.size / (1024 * 1024)).toFixed(1)} MB; the limit is ${maxMb} MB for a video`
  const name = file.name.toLowerCase()
  if (!/\.(mp4|m4v|3gp|3gpp|3g2)$/.test(name) && file.type && !/^video\/(mp4|3gpp|3gpp2)$/.test(file.type)) {
    return `${file.name} is not an MP4 or 3GP file; record or export the video as MP4`
  }
  return null
}

// The message for the first file over the limit, or null. Saves an upload the API would refuse.
export function oversized(files: File[], maxMb: number): string | null {
  const limit = maxMb * 1024 * 1024
  const big = files.find((f) => f.size > limit)
  if (!big) return null
  const size = (big.size / (1024 * 1024)).toFixed(1)
  return `${big.name} is ${size} MB; the limit is ${maxMb} MB per photo`
}
