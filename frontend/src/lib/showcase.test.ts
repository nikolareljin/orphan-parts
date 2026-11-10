import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PAIRS, SHOWCASE_SEEN, builtSrc, partSrc, remember, seen, stepAfter } from './showcase'
import Showcase from '../components/Showcase'

function memory(): Storage {
  const kept = new Map<string, string>()
  return {
    getItem: (k: string) => kept.get(k) ?? null,
    setItem: (k: string, v: string) => void kept.set(k, v),
  } as Storage
}

const refusing = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('Showcase', () => {
  it('shows on the first visit only: remembered once shown', () => {
    const storage = memory()
    expect(seen(storage)).toBe(false)
    remember(storage)
    expect(seen(storage)).toBe(true)
    expect(storage.getItem(SHOWCASE_SEEN)).toBe('1')
  })

  it('shows, and closes for the visit, where storage is blocked', () => {
    expect(seen(refusing)).toBe(false)
    expect(() => remember(refusing)).not.toThrow()
    expect(seen(undefined)).toBe(false)
  })

  it('goes through every part and what it becomes, then starts again', () => {
    let step = 0
    const shown: string[] = []
    for (let i = 0; i < PAIRS.length * 2; i++) {
      shown.push(`${PAIRS[Math.floor(step / 2)].name}:${step % 2 ? 'built' : 'part'}`)
      step = stepAfter(step)
    }
    expect(step).toBe(0)
    expect(shown.slice(0, 2)).toEqual(['joystick:part', 'joystick:built'])
    expect(new Set(shown).size).toBe(PAIRS.length * 2)
  })

  it('serves every image from the web host, none from the backend', () => {
    const files = Object.keys(import.meta.glob('../../public/showcase/*.webp')).map((f) => f.replace('../../public', ''))
    for (const p of PAIRS) {
      expect(files).toContain(partSrc(p))
      expect(files).toContain(builtSrc(p))
    }
  })

  it('opens on the first pair with a close button, and loads only the next pair ahead', () => {
    const html = renderToStaticMarkup(createElement(Showcase, { open: true }))
    expect(html).toContain('aria-label="Close"')
    expect(html).toContain('A spare joystick module')
    expect(html).toContain(partSrc(PAIRS[1]))
    expect(html).not.toContain(partSrc(PAIRS[2]))
    expect(renderToStaticMarkup(createElement(Showcase, { open: false }))).toBe('')
  })
})
