import { describe, expect, it } from 'vitest'
import { clipProblem, oversized, takePhotos } from './photos'

function file(name: string, size: number, type = ''): File {
  return new File([new Uint8Array(size)], name, { type })
}

describe('the rules a capture follows before it is sent', () => {
  it('keeps the first photos and counts the rest', () => {
    const { kept, dropped } = takePhotos([file('a.jpg', 1), file('b.jpg', 1), file('c.jpg', 1)], 2)
    expect(kept.map((f) => f.name)).toEqual(['a.jpg', 'b.jpg'])
    expect(dropped).toBe(1)
  })
  it('names the first photo over the limit', () => {
    expect(oversized([file('a.jpg', 10)], 1)).toBeNull()
    expect(oversized([file('big.jpg', 2 * 1024 * 1024)], 1)).toContain('big.jpg')
  })
  it('refuses an empty, an oversized or a non-MP4 clip, and takes the rest', () => {
    expect(clipProblem(file('clip.mp4', 0), 60)).toContain('empty')
    expect(clipProblem(file('clip.mp4', 61 * 1024 * 1024), 60)).toContain('limit is 60 MB')
    expect(clipProblem(file('clip.mov', 10, 'video/quicktime'), 60)).toContain('not an MP4')
    expect(clipProblem(file('clip.webm', 10, 'video/webm'), 60)).toContain('not an MP4')
    expect(clipProblem(file('clip.mp4', 10, 'video/mp4'), 60)).toBeNull()
    expect(clipProblem(file('clip.3gp', 10), 60)).toBeNull()
    expect(clipProblem(file('recording', 10, 'video/mp4'), 60)).toBeNull()
  })
})
