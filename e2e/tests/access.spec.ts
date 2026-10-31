import { expect, test, type Page } from '@playwright/test'
import { grayPng } from './png'

// These start without the session every other test carries: the two doors are the subject.
test.use({ storageState: { cookies: [], origins: [] } })

const code = process.env.E2E_ACCESS_CODE ?? ''
const sampleLine = 'Recorded answer for this sample photo'

async function readALabel(page: Page) {
  await page.getByLabel('Photos of the label').setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: grayPng() })
  await page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)').uncheck()
  await page.getByRole('button', { name: 'Read the label' }).click()
  await expect(page.getByRole('table', { name: 'Evidence' })).toBeVisible()
}

test('without a session the pages are the demo, and the code opens the rest', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.goto('/')
  // the pages are there for the visitor; the way in is a link in the header
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByText(/Demo: recorded answers only\. Sign in to save/)).toBeVisible()
  // the inventory shows what the owner made public; a save is what the code unlocks
  await page.getByRole('button', { name: 'My inventory' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Read a label' }).click()
  // a recorded answer says so in plain words for the visitor, above the result
  await readALabel(page)
  await expect(page.getByRole('note').filter({ hasText: sampleLine })).toBeVisible()

  await page.getByRole('button', { name: 'Sign in with the code' }).click()
  const gate = page.getByRole('form', { name: 'Access code' })
  await expect(gate).toBeVisible()
  await gate.getByLabel('Access code').fill('not the code')
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(gate.getByRole('alert')).toContainText('not the access code')

  await gate.getByLabel('Access code').fill(code)
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toHaveCount(0)
  await expect(page.getByText(/Demo: \d+ of \d+ calls used today/)).toBeVisible()
  // signed in, the same recorded reading carries only its small badge
  await readALabel(page)
  await expect(page.getByText('recorded answer', { exact: true })).toBeVisible()
  await expect(page.getByText(sampleLine)).toHaveCount(0)
  await page.getByRole('button', { name: 'My inventory' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)

  // the way out: the header's Sign out drops the page back to the demo, and it stays there
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0)
  await expect(page.getByText(/Demo: recorded answers only\. Sign in to save/)).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  const after = (await (await page.request.get('/api/access')).json()) as { granted: boolean }
  expect(after.granted).toBe(false)
  const write = await page.request.post('/api/items', { data: { item_type: 'kettle' } })
  expect(write.status()).toBe(403)
})

test('the API answers the demo visitor with recordings and refuses every write', async ({ request }) => {
  test.skip(!code, 'the stack runs without a gate')
  const listed = await request.get('/api/items')
  expect(listed.status()).toBe(200) // the public shelf, whatever is on it
  const refused = await request.get('/api/searches')
  expect(refused.status()).toBe(403)
  expect(((await refused.json()) as { detail: string }).detail).toContain('demo: the code unlocks saving')
  const write = await request.post('/api/items', { data: { item_type: 'kettle' } })
  expect(write.status()).toBe(403)
  const open = await request.get('/api/version')
  expect(open.status()).toBe(200)
  // the headline of the demo door: a try is answered, from the recordings, and spends nothing
  const tried = await request.post('/api/extract', {
    multipart: { photos: { name: 'label.png', mimeType: 'image/png', buffer: grayPng() } },
  })
  expect(tried.status()).toBe(200)
  expect(((await tried.json()) as { from_fixture: boolean }).from_fixture).toBe(true)
  // an item by its id is the inventory, not a try
  const peek = await request.post('/api/assess', { data: { need: { item_id: 1 }, candidate: { values: {} } } })
  expect(peek.status()).toBe(403)
  const profiles = await request.get('/api/profiles')
  expect(profiles.status()).toBe(200)
  const access = (await (await request.get('/api/access')).json()) as { gated: boolean; granted: boolean; live: boolean }
  expect(access).toEqual({ gated: true, granted: false, live: false, token: '', expires_at: 0 })
})
