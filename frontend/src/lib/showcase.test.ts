import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LAST_STEP, PAIRS, SHOWCASE_SEEN, WELCOME_HASH, askedFor, itemNamed, pairStep, builtSrc, partSrc, remember, seen, stepAfter } from './showcase'
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

  it('goes through every part and what it becomes once, then stays on the last drawing', () => {
    let step = 0
    const shown: string[] = []
    for (let i = 0; i < PAIRS.length * 2; i++) {
      shown.push(`${PAIRS[Math.floor(step / 2)].name}:${step % 2 ? 'built' : 'part'}`)
      step = stepAfter(step)
    }
    expect(shown.slice(0, 2)).toEqual(['joystick:part', 'joystick:built'])
    expect(new Set(shown).size).toBe(PAIRS.length * 2)
    expect(step).toBe(LAST_STEP)
    expect(stepAfter(LAST_STEP)).toBe(LAST_STEP)
  })

  it('steps to a part by hand, wrapping round; with reduced motion, to what it became', () => {
    expect(pairStep(1, false)).toBe(2)
    expect(pairStep(PAIRS.length, false)).toBe(0) // > after the last: the first again
    expect(pairStep(-1, false)).toBe(2 * (PAIRS.length - 1)) // < before the first: the last
    expect(pairStep(2, true)).toBe(5)
  })

  it('plays again at #welcome, whatever this browser remembers', () => {
    expect(WELCOME_HASH).toBe('#welcome')
    expect(askedFor('#welcome')).toBe(true)
    expect(askedFor('')).toBe(false)
    expect(askedFor('#inventory')).toBe(false)
  })

  it('finds the demo item of a part by its name, and says when this host has none', () => {
    const items = [
      { id: 7, name: 'Elegoo UNO R3 board' },
      { id: 9, name: ' Joystick module ' },
    ]
    expect(itemNamed(items, 'Joystick module')).toBe(9)
    expect(itemNamed(items, 'elegoo uno r3 board')).toBe(7)
    expect(itemNamed(items, 'HC-SR04 ultrasonic distance module')).toBeNull()
    for (const pair of PAIRS) expect(pair.item.length).toBeGreaterThan(0)
  })

  it('serves every image from the web host, none from the backend', () => {
    const files = Object.keys(import.meta.glob('../../public/showcase/*.webp')).map((f) => f.replace('../../public', ''))
    for (const p of PAIRS) {
      expect(files).toContain(partSrc(p))
      expect(files).toContain(builtSrc(p))
    }
  })

  it('links the shown part to its demo item', () => {
    const html = renderToStaticMarkup(createElement(Showcase, { open: true, onOpenItem: async () => true }))
    expect(html).toContain('See the Joystick module in the demo</button>')
  })

  it('keeps the pair before as drawn under the one fading in', () => {
    const html = renderToStaticMarkup(createElement(Showcase, { open: true }))
    // the first pair is current; nothing before it, and nothing drawn yet
    expect(html).not.toContain('is-before')
    expect(html).toContain('class="showcase-pair is-current"')
  })

  it('opens on the first pair with a close button, and loads only the next pair ahead', () => {
    const html = renderToStaticMarkup(createElement(Showcase, { open: true }))
    expect(html).toContain('aria-label="Close the welcome"')
    expect(html).toContain('aria-label="Previous part"')
    expect(html).toContain('aria-label="Next part"')
    // no way to the demo item unless the page can open one
    expect(html).not.toContain('in the demo</button>')
    expect(html).toContain('class="showcase-stage" aria-hidden="true"')
    // the live region is there and quiet: only < and > put words in it
    expect(html).toContain('aria-live="polite"></p>')
    expect(html).toContain('A spare joystick module')
    expect(html).toContain(partSrc(PAIRS[1]))
    expect(html).not.toContain(partSrc(PAIRS[2]))
    // what the part becomes is not said before its turn
    expect(html).toContain('<span class="showcase-arrow" aria-hidden="true">')
    expect(renderToStaticMarkup(createElement(Showcase, { open: false }))).toBe('')
  })
})
