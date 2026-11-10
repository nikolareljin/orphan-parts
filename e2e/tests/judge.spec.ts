import { expect, test } from '@playwright/test'
import { SIGNED_OUT } from '../global-setup'
import { grayPng } from './png'

// A judge's code (./dev keys issue --scope judge): issued by ./dev e2e before the run. It reads
// the demo set read-only and keeps what it adds as its own.
const judgeCode = process.env.E2E_JUDGE_CODE ?? ''
const stamp = Date.now().toString(36)

test('a judge reads the demo set read-only and edits what it adds', async ({ browser, request }) => {
  test.skip(!judgeCode, 'no judge code was issued for this run')
  // the owner (the run's session) puts an item on the public shelf
  const shown = `Demo shelf lamp ${stamp}`
  const made = await request.post('/api/items', { data: { item_type: 'lamp', name: shown, notes: 'the owner only' } })
  expect(made.status()).toBe(201)
  const demoId = ((await made.json()) as { id: number }).id
  expect((await request.post(`/api/items/${demoId}/public`, { data: { public: true } })).status()).toBe(200)

  // the judge signs in with its own code, in a browser of its own
  const context = await browser.newContext({ storageState: SIGNED_OUT })
  const page = await context.newPage()
  await page.goto('/')
  await page.getByRole('button', { name: 'Sign in with the code' }).click()
  const gate = page.getByRole('form', { name: 'Access code' })
  await gate.getByLabel('Access code').fill(judgeCode)
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await expect(page.getByText(/Judge access: \d+ live calls? left today, \$\d+\.\d\d left/)).toBeVisible()

  // the demo item: there, read-only, its private notes left out
  await page.getByRole('button', { name: 'My inventory' }).click()
  const items = page.getByRole('table', { name: 'Items' })
  await items.getByRole('row', { name: shown }).getByRole('button', { name: 'Open' }).click()
  const demoPanel = page.getByRole('article', { name: `Item ${shown}` })
  await expect(demoPanel.getByRole('button', { name: 'Delete' })).toBeDisabled()
  await expect(demoPanel.getByText('the owner only')).toHaveCount(0)
  await expect(demoPanel.getByText(/Judge access: the demo set is read-only/)).toBeVisible()
  // and the server says the same, whatever the page shows
  const refused = await page.request.delete(`/api/items/${demoId}`)
  expect(refused.status()).toBe(403)
  expect(((await refused.json()) as { detail: string }).detail).toContain('judge access')
  await page.getByRole('dialog', { name: `Item #${demoId}` }).getByRole('button', { name: 'Close' }).click()

  // a photo of its own: read, saved, its own to change
  await page.getByRole('button', { name: 'Read a label' }).click()
  await page.getByLabel('Photos of the label').setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: grayPng() })
  await page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)').uncheck()
  await page.getByRole('button', { name: 'Read the label' }).click()
  await expect(page.getByRole('table', { name: 'Evidence' })).toBeVisible()
  const own = `Judge charger ${stamp}`
  await page.getByLabel('Name').fill(own)
  await page.getByRole('button', { name: 'Save privately' }).click()
  await expect(page.getByRole('heading', { name: 'My inventory' })).toBeVisible()
  await items.getByRole('row', { name: own }).getByRole('button', { name: 'Open' }).click()
  const ownPanel = page.getByRole('article', { name: `Item ${own}` })
  await expect(ownPanel.getByRole('button', { name: 'Delete' })).toBeEnabled()
  await expect(ownPanel.getByRole('button', { name: 'Save details' }).first()).toBeVisible()
  await context.close()

  // the owner's other browsers never see the judge's item on the public shelf
  const visitor = await browser.newContext({ storageState: SIGNED_OUT })
  const listed = (await (await visitor.request.get('/api/items')).json()) as { name: string }[]
  expect(listed.map((i) => i.name)).not.toContain(own)
  await visitor.close()
})
