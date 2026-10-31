import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { grayPng } from './png'

// A part the app cannot tie to its device asks for the device; a search can look on the web.
const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const prompt = "We couldn't tell which device this part came from."

async function createAgitator(request: APIRequestContext, name: string): Promise<number> {
  const res = await request.post('/api/items', { data: { name, item_type: 'blender agitator', profile: 'blender_agitator' } })
  expect(res.status()).toBe(201)
  return ((await res.json()) as { id: number }).id
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  return page.getByRole('article', { name: `Item ${name}` })
}

test('a part with no device asks for it, and the answer clears the question', async ({ page, request }) => {
  const name = `Agitator words ${stamp}`
  await createAgitator(request, name)
  const panel = await openItem(page, name)
  const card = panel.getByRole('region', { name: 'Which device it came from' })
  await expect(card).toContainText(prompt)
  await expect(card).toContainText('the label under its base is best')
  await card.getByLabel('Device it came from').fill('Hamilton Beach drink mixer, model 729')
  await card.getByRole('button', { name: 'Save' }).click()
  await expect(card).toHaveCount(0)
  await expect(panel.getByRole('table', { name: 'Fields' })).toContainText('Hamilton Beach drink mixer, model 729')
})

test('a photo of the device is kept and the model read off it answers the question', async ({ page, request }) => {
  const name = `Agitator photo ${stamp}`
  await createAgitator(request, name)
  const panel = await openItem(page, name)
  const card = panel.getByRole('region', { name: 'Which device it came from' })
  await card.getByLabel('Add a photo of the device').setInputFiles({ name: 'base.png', mimeType: 'image/png', buffer: grayPng() })
  // the recorded label reading gives a brand and a model number
  await expect(card).toHaveCount(0)
  await expect(panel.getByRole('table', { name: 'Fields' })).toContainText('Orbital Power OP-65N')
  await expect(panel.getByRole('img', { name: 'Item photo 1' })).toBeVisible()
})

test('Search the web brings back pages as listings with their links', async ({ page, request }) => {
  const name = `Agitator web ${stamp}`
  const id = await createAgitator(request, name)
  expect((await request.post(`/api/items/${id}/fields`, { data: { field: 'parent_device_model', value: 'Hamilton Beach 729' } })).status()).toBe(200)
  const title = `metal agitator web ${stamp}`
  const created = await request.post('/api/searches', { data: { need_item_id: id, title, max_price: 20 } })
  expect(created.status()).toBe(201)

  await page.goto('/')
  await page.getByRole('button', { name: 'Find a part' }).click()
  await page.getByRole('row', { name: new RegExp(title) }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Search ${title}` })
  const plan = panel.getByRole('region', { name: 'Plan the search' })
  await plan.getByRole('button', { name: 'Search the web' }).click()
  await expect(plan).toContainText('Added 3 pages to the listings. 1 left out')

  const ranked = panel.getByRole('list', { name: 'Listings brought back, ranked' })
  const items = ranked.getByRole('listitem').filter({ has: page.locator('.listing-text') })
  await expect(items).toHaveCount(3)
  await expect(ranked).toContainText('found on the web')
  const link = ranked.getByRole('link', { name: 'example.org' }).first()
  await expect(link).toHaveAttribute('href', /^https:\/\/example\.org\//)
  await expect(link).toHaveAttribute('target', '_blank')

  // the same pages again are not added twice
  await plan.getByRole('button', { name: 'Search the web' }).click()
  await expect(plan).toContainText('Added 0 pages to the listings.')
  await expect(items).toHaveCount(3)
})

test.describe('the demo visitor', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  const code = process.env.E2E_ACCESS_CODE ?? ''

  test('reads the question about the device and gets nothing to fill in', async ({ page, playwright, baseURL }) => {
    test.skip(!code, 'the stack runs without a gate')
    const owner = await playwright.request.newContext({ baseURL })
    expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
    const name = `Agitator visitor ${stamp}`
    const id = await createAgitator(owner, name)
    expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
    try {
      const panel = await openItem(page, name)
      const card = panel.getByRole('region', { name: 'Which device it came from' })
      await expect(card).toContainText(prompt)
      await expect(card.getByRole('textbox')).toHaveCount(0)
      await expect(card.locator('input[type="file"]')).toHaveCount(0)
      await expect(card).toContainText('Sign in with the access code')
    } finally {
      await owner.post(`/api/items/${id}/public`, { data: { public: false } })
      await owner.dispose()
    }
  })
})
