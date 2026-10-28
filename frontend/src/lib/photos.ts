import type { Limits } from './api'

// Used until /api/version has answered; the backend defaults are the same.
export const DEFAULT_LIMITS: Limits = { max_photos: 4, max_upload_mb: 12 }

export function takePhotos(files: File[], max: number): { kept: File[]; dropped: number } {
  const kept = files.slice(0, Math.max(max, 0))
  return { kept, dropped: files.length - kept.length }
}

// The message for the first file over the limit, or null. Saves an upload the API would refuse.
export function oversized(files: File[], maxMb: number): string | null {
  const limit = maxMb * 1024 * 1024
  const big = files.find((f) => f.size > limit)
  if (!big) return null
  const size = (big.size / (1024 * 1024)).toFixed(1)
  return `${big.name} is ${size} MB; the limit is ${maxMb} MB per photo`
}
