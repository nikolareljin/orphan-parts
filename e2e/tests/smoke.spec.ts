import { expect, test, type Page } from '@playwright/test'

// A fast tour as the demo visitor, on a desktop and on a phone: every page, one public item
// with each of its sections, and each "?" on the pages. Nothing in the console, no request
// refused or failed, and on the phone nothing wider than the screen (an open note included).
const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const PAGES = ['Read a label', 'Inbox', 'My inventory', 'Find a part', 'Build and reuse', 'Profile']

function watch(page: Page): string[] {
  const problems: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console: ${m.text()}`)
  })
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))
  page.on('requestfailed', (r) => {
    if (!r.failure()?.errorText.includes('ERR_ABORTED')) problems.push(`failed: ${r.method()} ${r.url()}`)
  })
  page.on('response', (r) => {
    if (r.status() >= 400) problems.push(`HTTP ${r.status()}: ${r.request().method()} ${r.url()}`)
  })
  return problems
}

async function pageWidth(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
}

for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 900 }],
  ['phone', { width: 390, height: 844 }],
] as const) {
  test(`the visitor's tour on a ${name} is clean`, async ({ browser, request }) => {
    // every page and every note on it, beside five other workers
    test.setTimeout(120_000)
    // a public item of the owner's, for the visitor to open
    const item = `Smoke tour item ${name} ${stamp}`
    const created = await request.post('/api/items', { data: { item_type: 'adapter', name: item } })
    expect(created.status()).toBe(201)
    const id = ((await created.json()) as { id: number }).id
    expect((await request.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)

    // a first visit on purpose: the welcome card is in the page whose width is checked
    const context = await browser.newContext({ viewport, storageState: { cookies: [], origins: [] } })
    const page = await context.newPage()
    const problems = watch(page)
    await page.goto('/')
    const nav = page.getByRole('navigation', { name: 'Pages' })
    for (const label of PAGES) {
      await nav.getByRole('button', { name: label, exact: true }).click()
      await expect(page.getByRole('heading', { level: 2, name: label })).toBeVisible()
      await expect(page.getByText('Loading…')).toHaveCount(0)
      const tips = page.locator('main button.help-tip-toggle')
      for (let i = 0; i < (await tips.count()); i++) {
        const tip = tips.nth(i)
        if (!(await tip.isVisible())) continue
        await tip.click()
        await expect(page.locator('.help-tip-pop')).toBeVisible()
        expect(await pageWidth(page), `${label}: an open note runs past the screen`).toBeLessThanOrEqual(1)
        await page.keyboard.press('Escape')
      }
      expect(await pageWidth(page), `${label} is wider than the screen`).toBeLessThanOrEqual(1)
    }

    await nav.getByRole('button', { name: 'My inventory', exact: true }).click()
    await page.getByRole('table', { name: 'Items' }).getByRole('row', { name: item }).getByRole('button', { name: 'Open' }).click()
    const panel = page.getByRole('article', { name: `Item ${item}` })
    await expect(panel).toBeVisible()
    // the visitor reads the facts; nothing there offers a write the server would refuse
    await expect(panel.getByRole('button', { name: 'Add field' })).toHaveCount(0)
    await expect(panel.getByRole('button', { name: 'Separate' })).toHaveCount(0)
    await expect(panel.getByRole('combobox', { name: /^Plan/ })).toBeDisabled()
    await expect(panel.getByRole('button', { name: 'History' })).toHaveCount(0)
    const sections = page.getByRole('navigation', { name: 'Sections' }).getByRole('button')
    for (let i = 0; i < (await sections.count()); i++) await sections.nth(i).click()
    expect(await pageWidth(page)).toBeLessThanOrEqual(1)

    expect(problems).toEqual([])
    await context.close()
  })
}
