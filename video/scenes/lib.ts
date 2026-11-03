import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { test as base, expect, type Locator, type Page } from '@playwright/test'

// What every scene shares: a visible cursor drawn into the page (a recorded browser has none),
// moves and clicks paced for the camera, and the take kept as <shot>.webm beside <shot>.json,
// which says where the picture is ready (the assembler cuts from there) and the wall-clock
// window of the take (the generator matches it against the backend's log for stand-in answers).

const OUT = process.env.SCENES_OUT ?? 'out'

// An arrow cursor in the top layer: a manual popover, shown again whenever a modal dialog
// opens, so it stays above the dialog; it never takes a click.
const CURSOR = `
(() => {
  if (window.__cursor) return
  window.__cursor = true
  const add = () => {
    const el = document.createElement('div')
    el.setAttribute('popover', 'manual')
    el.id = 'video-cursor'
    el.style.cssText = 'position:fixed;inset:auto;left:0;top:0;margin:0;padding:0;border:0;background:transparent;width:28px;height:28px;pointer-events:none;overflow:visible;transform:translate(-100px,-100px);transition:none'
    el.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 17 L12.5 26 L16 24.5 L12 15.5 L19.5 15.5 Z" fill="#111827" stroke="#ffffff" stroke-width="1.8" stroke-linejoin="round"/></svg>'
    document.body.appendChild(el)
    const show = () => { try { el.hidePopover() } catch {} ; try { el.showPopover() } catch {} }
    show()
    let open = 0
    new MutationObserver(() => {
      const now = document.querySelectorAll('dialog[open]').length
      if (now !== open) { open = now; show() }
    }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'], childList: true })
    document.addEventListener('mousemove', (e) => { el.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)' }, true)
    document.addEventListener('mousedown', () => { el.style.scale = '0.85' }, true)
    document.addEventListener('mouseup', () => { el.style.scale = '1' }, true)
  }
  if (document.body) add(); else document.addEventListener('DOMContentLoaded', add)
})()
`

export class Scene {
  readonly t0 = Date.now()
  private start = 0
  private readonly marks: Record<string, number> = {}
  private x = 800
  private y = 450

  constructor(
    readonly page: Page,
    readonly shot: string,
  ) {}

  private now(): number {
    return (Date.now() - this.t0) / 1000
  }

  /** The picture from here on is the shot: the assembler cuts the take from this point. */
  async ready(): Promise<void> {
    await this.settle()
    await this.page.mouse.move(this.x, this.y)
    this.start = this.now()
  }

  mark(name: string): void {
    this.marks[name] = this.now()
  }

  async settle(ms = 400): Promise<void> {
    await this.page.waitForLoadState('networkidle')
    // no spinner or "…" busy label on screen
    await expect(this.page.locator('[aria-busy="true"]')).toHaveCount(0)
    await this.page.waitForTimeout(ms)
  }

  async hold(ms: number): Promise<void> {
    await this.page.waitForTimeout(ms)
  }

  /** Into view smoothly, centered, before the cursor goes to it. */
  async reveal(target: Locator, block: 'center' | 'start' | 'end' = 'center'): Promise<void> {
    await target.waitFor({ state: 'visible' })
    const moved = await target.evaluate((el, b) => {
      const r = el.getBoundingClientRect()
      const inView = r.top >= 60 && r.bottom <= window.innerHeight - 40
      if (!inView) el.scrollIntoView({ behavior: 'smooth', block: b })
      return !inView
    }, block)
    if (moved) await this.page.waitForTimeout(900)
  }

  /** The cursor glides to the middle of the target. */
  async point(target: Locator, steps = 10): Promise<void> {
    await this.reveal(target)
    const box = await target.boundingBox()
    if (!box) throw new Error(`${this.shot}: nothing to point at`)
    const x = box.x + Math.min(box.width / 2, 60)
    const y = box.y + box.height / 2
    await this.page.mouse.move(x, y, { steps })
    this.x = x
    this.y = y
  }

  async click(target: Locator, after = 500): Promise<void> {
    await this.point(target)
    await this.page.waitForTimeout(180)
    await target.click()
    await this.page.waitForTimeout(after)
  }

  async type(target: Locator, text: string, delay = 28): Promise<void> {
    await this.click(target, 150)
    await target.fill('')
    await target.pressSequentially(text, { delay })
    await this.page.waitForTimeout(250)
  }

  /** A slow scroll of the page or the open dialog by a number of pixels. */
  async scroll(dy: number, ms = 1200): Promise<void> {
    const steps = Math.max(10, Math.round(ms / 40))
    for (let i = 0; i < steps; i++) {
      await this.page.mouse.wheel(0, dy / steps)
      await this.page.waitForTimeout(ms / steps)
    }
    await this.page.waitForTimeout(250)
  }

  write(extra: Record<string, unknown> = {}): void {
    mkdirSync(join(OUT, 'takes'), { recursive: true })
    const take = { shot: this.shot, start: this.start, end: this.now(), marks: this.marks, wall: { from: this.t0, to: Date.now() }, ...extra }
    writeFileSync(join(OUT, 'takes', `${this.shot}.json`), JSON.stringify(take, null, 2) + '\n')
  }
}

export const test = base.extend<{ scene: Scene }>({
  scene: async ({ page }, use, info) => {
    await page.addInitScript(CURSOR)
    const shot = info.title.split(' ')[0]
    const scene = new Scene(page, shot)
    await use(scene)
    scene.write()
    const video = page.video()
    await page.close()
    if (video) {
      mkdirSync(join(OUT, 'takes'), { recursive: true })
      await video.saveAs(join(OUT, 'takes', `${shot}.webm`))
    }
  },
})

export { expect }

/** The item dialog of a named item, opened from My inventory. */
export async function openItem(scene: Scene, name: string): Promise<Locator> {
  const { page } = scene
  await scene.click(page.getByRole('button', { name: 'My inventory', exact: true }))
  const row = page.getByRole('table', { name: 'Items' }).getByRole('row', { name: new RegExp(name) })
  await scene.click(row.getByRole('button', { name: 'Open' }))
  return page.getByRole('article', { name: new RegExp(`^Item ${name}`) })
}
