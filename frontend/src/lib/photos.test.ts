import { describe, expect, it } from 'vitest'
import { DEFAULT_LIMITS, oversized, takePhotos } from './photos'

const file = (name: string, bytes: number): File => new File([new Uint8Array(bytes)], name, { type: 'image/jpeg' })

describe('takePhotos', () => {
  it('keeps the first files up to the limit and counts the rest', () => {
    const files = ['a', 'b', 'c', 'd', 'e'].map((n) => file(`${n}.jpg`, 1))
    const { kept, dropped } = takePhotos(files, 4)
    expect(kept.map((f) => f.name)).toEqual(['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])
    expect(dropped).toBe(1)
  })

  it('drops nothing under the limit', () => {
    expect(takePhotos([file('a.jpg', 1)], DEFAULT_LIMITS.max_photos).dropped).toBe(0)
  })
})

describe('oversized', () => {
  it('names the first file over the limit with its size', () => {
    const files = [file('ok.jpg', 1024), file('big.jpg', 2 * 1024 * 1024 + 1)]
    expect(oversized(files, 2)).toBe('big.jpg is 2.0 MB; the limit is 2 MB per photo')
  })

  it('accepts a file exactly at the limit', () => {
    expect(oversized([file('edge.jpg', 2 * 1024 * 1024)], 2)).toBeNull()
  })
})
