import { expect, openItem, section, test } from './lib'
import type { Locator, Page } from '@playwright/test'

// Examples of what the models wrote for the demo set (docs/start/examples.md): the build
// proposals and the four selected builds with every picture drawn of them, the Decide cards,
// the price guidance and the drafts, the searches, and the inventory with a reading. Each is
// one element shot whole (Shots.element), from the recorded answers the hosted demo replays.
// Runs right after 02-search.spec.ts (02b sorts there): the agitator's device is answered and its
// web search run, and nothing later (a project drawn again, more proposals) is in the pictures yet.
// It only reads, so the specs after it find the set as before.

test.describe.configure({ mode: 'serial' })

const SELECTED = [
  ['nas', 'Custom NAS'],
  ['arcade', 'Arcade coffee table'],
  ['calendar', 'Smart desk calendar'],
  ['automation', 'Home automation server'],
] as const
const PROPOSED = [
  ['kitchen', 'Kitchen home-automation dashboard'],
  ['mirror', 'Smart mirror'],
  ['weather', 'weather station'],
  ['parking', 'Garage parking helper'],
] as const

/** The project of that title, opened from Build and reuse. */
async function project(page: Page, title: string): Promise<Locator> {
  await page.goto('/#build')
  const table = page.getByRole('table', { name: 'Projects' })
  await table.getByRole('row', { name: new RegExp(title, 'i') }).first().getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: /^Project / })
  await expect(panel).toBeVisible()
  return panel
}

/** Every picture drawn of the project, loaded. */
async function drawings(panel: Locator): Promise<Locator> {
  const gallery = panel.locator('.draw-it')
  const pictures = gallery.getByRole('img', { name: /^Illustrative picture/ })
  await expect(pictures.first()).toBeVisible()
  for (const img of await pictures.all()) {
    await img.scrollIntoViewIfNeeded()
    await expect.poll(() => img.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  }
  return gallery
}

function close(page: Page): Promise<void> {
  return page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
}

test.describe('signed in', () => {
  test('the proposals and the four selected builds', async ({ shots, page }) => {
    await page.goto('/#build')
    await shots.element('01-proposals', page.getByRole('table', { name: 'Projects' }))
    for (const [key, title] of SELECTED) {
      const panel = await project(page, title)
      await shots.element(`02-${key}-drawings`, await drawings(panel))
      await shots.element(`03-${key}-panel`, page.getByRole('dialog'), '.project-panel .draw-it, .project-panel .packs')
      const pack = panel.getByRole('region', { name: 'Build pack' })
      await expect(pack.getByLabel(/^Build pack \d/)).toBeVisible()
      await shots.element(`04-${key}-pack`, pack)
      await close(page)
    }
  })

  test('price guidance and the sell draft, the give draft', async ({ shots, page }) => {
    let item = await openItem(page, 'EVGA GeForce 9500 GT graphics card')
    await section(item, 'Value')
    await shots.element('20-9500gt-value', item.getByRole('region', { name: 'What is it worth?' }))
    await section(item, 'Sell or give away')
    await shots.element('21-9500gt-sell-draft', item.getByRole('region', { name: 'Marketplace handoff' }))
    await close(page)
    item = await openItem(page, 'iPhone charging port and earpiece flex cables')
    await section(item, 'Sell or give away')
    await shots.element('22-flex-give-draft', item.getByRole('region', { name: 'Marketplace handoff' }))
  })

  test('a search plan: the NAS processor the build still needs', async ({ shots, page }) => {
    // the plan written when the build was selected: phrasings as Marketplace links, a pattern
    await page.goto('/#find')
    await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: /A processor that fits the board's socket/ }).first().getByRole('button', { name: 'Open' }).click()
    const plan = page.getByRole('article', { name: /^Search A processor that fits/ }).getByRole('region', { name: 'Plan the search' })
    await expect(plan.getByRole('list', { name: 'Search phrasings' }).getByRole('listitem').first()).toBeVisible()
    await shots.element('30-nas-cpu-plan', plan)
  })

  test('the agitator search: web finds ranked, Check fit, the seller', async ({ shots, page }) => {
    await page.goto('/#find')
    await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: /all-metal agitator rod/ }).getByRole('button', { name: 'Open' }).click()
    const panel = page.getByRole('article', { name: /^Search all-metal agitator rod/ })
    const plan = panel.getByRole('region', { name: 'Plan the search' })
    const ranked = panel.getByRole('list', { name: 'Listings brought back, ranked' })
    let web = ranked.getByRole('listitem').filter({ hasText: 'found on the web' }).first()
    if (!(await web.count())) {
      await plan.getByRole('button', { name: 'Search the web' }).click()
      await expect(plan).toContainText(/Added \d+ pages? to the listings/, { timeout: 120_000 })
      web = ranked.getByRole('listitem').filter({ hasText: 'found on the web' }).first()
    }
    // checked once already (02-search.spec.ts): the fit kept is shown again, else checked now
    const shown = web.getByRole('button', { name: 'Show the fit' })
    await ((await shown.count()) ? shown : web.getByRole('button', { name: 'Check fit' })).click()
    await expect(web.getByLabel(/^Fit of listing/)).toBeVisible({ timeout: 120_000 })
    await shots.element('31-agitator-ranked', ranked)
    await shots.element('32-agitator-fit', web)
  })

  test('the NAS power supply, searched on the web', async ({ shots, page }) => {
    await page.goto('/#find')
    await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: /ATX power supply for a home NAS/ }).first().getByRole('button', { name: 'Open' }).click()
    const panel = page.getByRole('article', { name: /^Search ATX power supply/ })
    await expect(panel).toBeVisible()
    await shots.element('33-nas-psu-search', panel.getByRole('list', { name: 'Listings brought back, ranked' }))
  })

  test('the inventory and its saved results', async ({ shots, page }) => {
    await page.goto('/#inventory')
    await expect(page.getByRole('table', { name: 'Items' })).toBeVisible()
    await shots.take('40-inventory')
  })
})

test.describe('the visitor', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('the visitor reads the builds', async ({ shots, page }) => {
    await page.goto('/#build')
    await shots.take('50-visitor-build')
    let panel = await project(page, 'Custom NAS')
    await shots.element('51-visitor-nas', page.getByRole('dialog'), '.project-panel .packs')
    await close(page)
    for (const [key, title] of PROPOSED) {
      panel = await project(page, title)
      await drawings(panel)
      await shots.element(`52-visitor-${key}`, page.getByRole('dialog'))
      await close(page)
    }
  })

  test('the visitor reads the Decide cards', async ({ shots, page }) => {
    for (const [key, name] of [
      ['build', 'Dell U2419H monitor, 24 inch'],
      ['sell', 'Sun flat panel monitor'],
      ['give', 'Older ThinkPad, type 9461'],
      ['spare', 'Phone battery test board'],
    ] as const) {
      const item = await openItem(page, name)
      const cards = item.getByRole('region', { name: 'What to do with it' })
      await shots.element(`60-visitor-decide-${key}`, cards)
      await close(page)
    }
  })

  test('the visitor reads three decisions whole', async ({ shots, page }) => {
    // What should I do with it?: the Decide section (the plan chosen, the recommendation, the
    // three cards with any reuse card's drawing) and the item's own drawings, the rest of the
    // item left out; a sale, a keep and a build
    const rest = 'dialog [data-section="facts"], dialog [data-section="value"], dialog [data-section="sell"], dialog [data-section="fit"]'
    for (const [key, name] of [
      ['sell', 'Sun flat panel monitor'],
      ['keep', 'Joystick module'],
      ['build', 'ThinkPad T510'],
    ] as const) {
      const item = await openItem(page, name)
      await expect(item.getByRole('region', { name: 'What to do with it' })).toBeVisible()
      const drawn = item.getByRole('img', { name: /^Illustrative picture/ })
      for (const img of await drawn.all()) {
        await img.scrollIntoViewIfNeeded()
        await expect.poll(() => img.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
      }
      await shots.element(`65-visitor-what-to-do-${key}`, page.getByRole('dialog'), rest)
      if (key === 'sell') {
        await section(item, 'Value')
        await shots.element('66-visitor-sun-value', item.getByRole('region', { name: 'What is it worth?' }))
        await shots.element('67-visitor-sun-draft', item.getByRole('region', { name: 'Marketplace handoff' }))
      }
      await close(page)
    }
  })

  test('the visitor reads the drafts', async ({ shots, page }) => {
    let item = await openItem(page, 'EVGA GeForce 9500 GT graphics card')
    await shots.element('61-visitor-9500gt-draft', item.getByRole('region', { name: 'Marketplace handoff' }))
    await close(page)
    item = await openItem(page, 'iPhone charging port and earpiece flex cables')
    await shots.element('62-visitor-flex-draft', item.getByRole('region', { name: 'Marketplace handoff' }))
  })

  test('the visitor reads an item and a label', async ({ shots, page }) => {
    await page.goto('/#inventory')
    await shots.element('70-visitor-inventory', page.getByRole('table', { name: 'Items' }))
    // its photos as shared (private details blacked out) and every value with where it came from
    const item = await openItem(page, 'Kingston A400 480 GB SSD')
    await shots.element('71-visitor-item', item.locator(':scope > [data-section="facts"]'))
    // the reading with the region SAM 3.1 found: the label of the Sun monitor
    await page.goto('/')
    const sun = page.getByRole('group', { name: 'Sun flat panel monitor' })
    await sun.getByRole('button', { name: 'Select all photos of this item' }).click()
    await page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)').check()
    await page.getByRole('button', { name: 'Read the label' }).click()
    const reading = page.getByRole('article', { name: /^Reading: Sun flat panel monitor/ })
    await expect(reading).toBeVisible({ timeout: 60_000 })
    // the photo with SAM 3.1's region drawn smaller than on the page, so the picture stays light
    await shots.element('72-visitor-reading', reading, '', '.sample-result img.overlay { max-width: 400px !important; }')
  })
})
