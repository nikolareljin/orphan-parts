import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// The "?" beside a heading: a tap opens a short note with a link to the docs; Escape, a click
// elsewhere or the close button end it. In the item dialog, Escape closes the note, not the dialog.

const code = process.env.E2E_ACCESS_CODE ?? ''
const stamp = Date.now().toString(36)

async function createItem(request: APIRequestContext, name: string): Promise<number> {
  const res = await request.post('/api/items', { data: { name, item_type: 'blender agitator' } })
  expect(res.status()).toBe(201)
  return ((await res.json()) as { id: number }).id
}

async function openTip(page: Page, topic: string) {
  const toggle = page.getByRole('button', { name: `Help: ${topic}`, exact: true })
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  const note = page.getByRole('group', { name: `About: ${topic}` })
  await expect(note).toBeVisible()
  return { toggle, note }
}

async function openItem(page: Page, name: string) {
  await page.goto('/#inventory')
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  return page.getByRole('article', { name: `Item ${name}` })
}

test.describe('signed in', () => {
  test('Find a part: the note opens, links to the docs and closes on Escape', async ({ page }) => {
    await page.goto('/#find')
    const { toggle, note } = await openTip(page, 'part searches')
    await expect(note).toContainText('never searches, fetches or posts on Marketplace')
    await expect(note.getByRole('link', { name: 'More in the docs' })).toHaveAttribute('href', 'https://nikolareljin.github.io/orphan-parts/guides/search/')
    await page.keyboard.press('Escape')
    await expect(note).toHaveCount(0)
    await expect(toggle).toBeFocused()

    // a click elsewhere closes it too
    await openTip(page, 'starting a search')
    await page.getByRole('heading', { name: 'Find a part' }).click()
    await expect(page.getByRole('group', { name: 'About: starting a search' })).toHaveCount(0)
  })

  test('item dialog: Escape closes the note and leaves the dialog open; the close button works', async ({ page, request }) => {
    const name = `Help item ${stamp}`
    await createItem(request, name)
    const panel = await openItem(page, name)

    const { note } = await openTip(page, 'scenario cards')
    await expect(note).toContainText('three cards')
    await page.keyboard.press('Escape')
    await expect(note).toHaveCount(0)
    await expect(panel).toBeVisible()

    const facts = await openTip(page, 'confirming what was read')
    await expect(facts.note).toContainText('Accept or Reject')
    await facts.note.getByRole('button', { name: 'Dismiss help' }).click()
    await expect(facts.note).toHaveCount(0)
    await expect(facts.toggle).toBeFocused()
    await expect(panel).toBeVisible()
  })
})

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('the visitor gets the notes that say what is read-only', async ({ page, playwright, baseURL }) => {
    test.skip(!code, 'the stack runs without a gate')
    const owner = await playwright.request.newContext({ baseURL })
    expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
    const name = `Help public ${stamp}`
    const id = await createItem(owner, name)
    expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)

    try {
      await page.goto('/#find')
      const find = await openTip(page, 'part searches')
      await expect(find.note).toContainText('read-only')
      await page.keyboard.press('Escape')

      const header = await openTip(page, 'signing in')
      await expect(header.note).toContainText('Without the code you are in the demo')
      await page.keyboard.press('Escape')

      const panel = await openItem(page, name)
      const value = await openTip(page, 'price figures')
      await expect(value.note).toContainText('Four figures stay apart')
      await page.keyboard.press('Escape')
      await expect(value.note).toHaveCount(0)
      await expect(panel).toBeVisible()
    } finally {
      await owner.post(`/api/items/${id}/public`, { data: { public: false } })
      await owner.dispose()
    }
  })
})
