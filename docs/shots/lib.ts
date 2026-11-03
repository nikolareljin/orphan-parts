import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { test as base, expect, type Locator, type Page } from '@playwright/test'

// What every guide's shots share: a fixed clock and fixed times on the page (the same picture
// on every run), whatever could carry a secret blurred before the picture is taken, and the
// picture kept as SHOTS_OUT/png/<guide>/<nn-name>.png.

const OUT = process.env.SHOTS_OUT ?? 'out'
export const PHOTOS = process.env.SHOTS_PHOTOS ?? '/photos'
export const LAN_URL = process.env.SHOTS_LAN_URL ?? ''

// the day every shot is taken on, as far as the page can tell
const NOW = new Date('2026-11-04T10:30:00-05:00')
const SHOWN_TIME = '2026-11-04 10:30'

// Blurred in every shot: the pairing code (its QR carries a session; it is also swapped for a
// fixed pattern first, so no pairing is in any picture, blurred or not), any password or code
// field, and anything a spec marks with data-shot-blur.
const BLUR = `
img[alt="Pairing code for the phone"],
input[type="password"],
[data-shot-blur] { filter: blur(18px) !important; }
`

/** Times shown in lists ("2026-11-03 14:05") read as one fixed time, so a run repeats itself. */
async function steadyTimes(page: Page): Promise<void> {
  await page.evaluate((shown) => {
    const pattern = /\b20\d\d-\d\d-\d\d \d\d:\d\d\b/g
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeValue && pattern.test(node.nodeValue)) node.nodeValue = node.nodeValue.replace(pattern, shown)
      pattern.lastIndex = 0
    }
  }, SHOWN_TIME)
}

// a QR-like pattern of 25 x 25 modules from a fixed seed: what the pairing code is replaced with
const PATTERN = (() => {
  let seed = 7
  const cells: string[] = []
  for (let y = 0; y < 25; y++)
    for (let x = 0; x < 25; x++) {
      seed = (seed * 1103515245 + 12345) % 2147483648
      if (seed % 2) cells.push(`<rect x="${x}" y="${y}" width="1" height="1"/>`)
    }
  return `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 29 29"><rect x="-2" y="-2" width="29" height="29" fill="#fff"/>${cells.join('')}</svg>`)}`
})()

/** The pairing code swapped for the fixed pattern, focus and hover gone, every scroll at rest. */
async function steadyPage(page: Page): Promise<void> {
  await page.evaluate((pattern) => {
    for (const img of document.querySelectorAll<HTMLImageElement>('img[alt="Pairing code for the phone"]')) img.src = pattern
    ;(document.activeElement as HTMLElement | null)?.blur?.()
  }, PATTERN)
  const positions = () =>
    page.evaluate(() =>
      [document.scrollingElement, ...document.querySelectorAll('*')]
        .filter((el): el is Element => !!el && el.scrollTop > 0)
        .map((el) => el.scrollTop)
        .join(','),
    )
  // at rest: the same positions read three times, 200 ms apart
  let last = await positions()
  let same = 0
  for (let i = 0; i < 30 && same < 2; i++) {
    await page.waitForTimeout(200)
    const now = await positions()
    same = now === last ? same + 1 : 0
    last = now
  }
}

export class Shots {
  constructor(
    readonly page: Page,
    // the guide the next shots belong to; a spec may switch it for a step another guide shows
    public guide: string,
  ) {}

  /** No request in flight, no busy label, then a moment for the layout. */
  async settle(ms = 300): Promise<void> {
    await this.page.waitForLoadState('networkidle')
    await expect(this.page.locator('[aria-busy="true"]')).toHaveCount(0)
    await this.page.waitForTimeout(ms)
  }

  /** The element into view, at the top of the page or of the open dialog (or centered). */
  async show(target: Locator, block: 'start' | 'center' | 'end' = 'start'): Promise<void> {
    await target.waitFor({ state: 'visible' })
    // twice: photos that load once scrolled to (lazy) move what is under them, so the second
    // scroll lands where the first meant to, after they have
    for (let round = 0; round < 2; round++) {
      await target.evaluate((el, b) => el.scrollIntoView({ block: b, behavior: 'instant' }), block)
      await this.page
        .waitForFunction(() => [...document.images].every((img) => img.complete), undefined, { timeout: 5_000 })
        .catch(() => undefined)
      await this.page.waitForTimeout(150)
    }
  }

  /** The page as it is now, as <nn-name>.png of this guide. */
  async take(name: string): Promise<void> {
    await this.settle()
    await steadyPage(this.page)
    await steadyTimes(this.page)
    await this.page.mouse.move(0, 0)
    const dir = join(OUT, 'png', this.guide)
    mkdirSync(dir, { recursive: true })
    await this.page.screenshot({ path: join(dir, `${name}.png`), animations: 'disabled', caret: 'hide', style: BLUR })
  }

  /** One element alone (a project panel, a draft, the drawings), as <nn-name>.png of this guide:
   * the window made as tall as the element needs (up to MAX_TALL), so a dialog shows all of it
   * with no scroll, then back to 1280x800. `hide` names parts left out of this picture (shown in
   * a picture of their own), e.g. a project's build pack; `css` is more style for this picture
   * alone (a photo drawn smaller, say). */
  async element(name: string, target: Locator, hide = '', css = ''): Promise<void> {
    const page = this.page
    const size = page.viewportSize() ?? { width: 1280, height: 800 }
    await target.waitFor({ state: 'visible' })
    const style = `${hide ? `${hide} { display: none !important; }` : ''}${css}`
    const hidden = style ? await page.addStyleTag({ content: style }) : null
    // the element's height plus what a scrolling box in it (a dialog's body) or around it hides
    const needed = await target.evaluate((el) => {
      let extra = 0
      for (const box of [...el.querySelectorAll('*'), ...(function* () {
        for (let up = el.parentElement; up; up = up.parentElement) yield up
      })()]) {
        if (box.scrollHeight > box.clientHeight + 1 && getComputedStyle(box).overflowY !== 'visible') extra += box.scrollHeight - box.clientHeight
      }
      return el.getBoundingClientRect().height + extra
    })
    await page.setViewportSize({ width: size.width, height: Math.min(MAX_TALL, Math.max(size.height, Math.ceil(needed) + 160)) })
    try {
      // a box scrolled inside the element (a dialog's body) back at its top
      await target.evaluate((el) => el.querySelectorAll('*').forEach((box) => box.scrollTop > 0 && box.scrollTo({ top: 0, behavior: 'instant' })))
      await this.show(target)
      await this.settle()
      await steadyPage(page)
      await steadyTimes(page)
      await page.mouse.move(0, 0)
      const dir = join(OUT, 'png', this.guide)
      mkdirSync(dir, { recursive: true })
      await target.screenshot({ path: join(dir, `${name}.png`), animations: 'disabled', caret: 'hide', style: BLUR })
    } finally {
      await hidden?.evaluate((el) => el.remove())
      await page.setViewportSize(size)
    }
  }
}

// the tallest window an element shot opens (a long project panel is cut there)
const MAX_TALL = 4000

export const test = base.extend<{ shots: Shots }>({
  shots: async ({ page }, use, info) => {
    await page.clock.setFixedTime(NOW)
    // the guide is the spec's file name without its number: 03-profile.spec.ts is profile, and
    // 02b-examples.spec.ts (run between 02- and 03-) is examples
    const guide = info.file.replace(/^.*\/\d\d[a-z]?-/, '').replace(/\.spec\.ts$/, '')
    await use(new Shots(page, guide))
  },
})

export { expect }

/** The item dialog of a named item, opened from My inventory. */
export async function openItem(page: Page, name: string): Promise<Locator> {
  await page.goto('/#inventory')
  const row = page.getByRole('table', { name: 'Items' }).getByRole('row', { name: new RegExp(name) })
  await row.first().getByRole('button', { name: 'Open' }).click()
  const item = page.getByRole('article', { name: new RegExp(`^Item ${name}`) })
  await expect(item).toBeVisible()
  return item
}

// the item dialog's section links and the sections they lead to (Inventory.tsx)
const SECTION_IDS: Record<string, string> = {
  Facts: 'facts',
  Decide: 'decide',
  Value: 'value',
  'Sell or give away': 'sell',
  'Measure and fit': 'fit',
  Picture: 'picture',
}

/** A section of the open item, by the dialog's section links. */
export async function section(item: Locator, name: string): Promise<void> {
  await item.getByRole('navigation', { name: 'Sections' }).getByRole('button', { name, exact: true }).click()
  // the link scrolls smoothly; once it has, the section is put at the top again at once, so
  // the shot does not depend on where the smooth scroll happened to stop
  await item.page().waitForTimeout(1200)
  const id = SECTION_IDS[name]
  if (id) {
    await item
      .locator(`:scope > [data-section="${id}"]`)
      .evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'instant' }))
    await item.page().waitForTimeout(300)
  }
}
