import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { DOCS_BASE, HELP, docsUrl, helpNext, type HelpEntry } from '../lib/help'
import HelpTip from './HelpTip'

const entry: HelpEntry = { topic: 'test spot', text: 'What can be done here.', doc: 'guides/search/' }

function render(open = false, e: HelpEntry = entry): string {
  return renderToStaticMarkup(createElement(HelpTip, { entry: e, defaultOpen: open }))
}

describe('HelpTip', () => {
  it('is a "?" button named for its topic, closed at first', () => {
    const html = render()
    expect(html).toContain('<button type="button" class="link help-tip-toggle" aria-label="Help: test spot" aria-expanded="false">?</button>')
    expect(html).not.toContain('What can be done here.')
    expect(html).not.toContain('aria-controls')
  })

  it('shows the note, the docs link and a close button when open', () => {
    const html = render(true)
    expect(html).toContain('aria-expanded="true"')
    const controls = /aria-controls="([^"]+)"/.exec(html)?.[1]
    expect(controls).toBeTruthy()
    expect(html).toContain(`id="${controls}"`)
    expect(html).toContain('role="group"')
    expect(html).toContain('What can be done here.')
    expect(html).toContain(`href="${DOCS_BASE}guides/search/"`)
    expect(html).toContain('target="_blank"')
    expect(html).toContain('aria-label="Dismiss help"')
  })

  it('has no docs link when the entry names no page', () => {
    expect(render(true, { topic: 'x', text: 'y' })).not.toContain('More in the docs')
  })
})

describe('helpNext', () => {
  it('toggles on the "?" and closes on everything else', () => {
    expect(helpNext(false, 'toggle')).toBe(true)
    expect(helpNext(true, 'toggle')).toBe(false)
    for (const action of ['escape', 'outside', 'close'] as const) {
      expect(helpNext(true, action)).toBe(false)
      expect(helpNext(false, action)).toBe(false)
    }
  })
})

describe('HELP', () => {
  const entries = Object.entries(HELP) as [string, HelpEntry][]

  it('keeps every note to three sentences at most', () => {
    for (const [key, e] of entries) {
      // a sentence ends with a period followed by a space or the end; "3.1" is not one
      const sentences = e.text.split(/\.(?:\s|$)/).filter((s) => s.trim())
      expect(sentences.length, key).toBeLessThanOrEqual(3)
    }
  })

  it('links each note to a page of the docs site', () => {
    for (const [key, e] of entries) {
      expect(e.doc, key).toBeTruthy()
      expect(e.doc?.startsWith('/'), key).toBe(false)
      expect(docsUrl(e.doc ?? '')).toMatch(/^https:\/\/nikolareljin\.github\.io\/orphan-parts\/[a-z-]+\/[a-z0-9-]+\/(#[a-z0-9-]+)?$/)
    }
  })
})
