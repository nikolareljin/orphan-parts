import { expect, test } from '@playwright/test'
import { grayPng } from './png'

// These start without the session every other test carries: the two doors are the subject.
test.use({ storageState: { cookies: [], origins: [] } })

const code = process.env.E2E_ACCESS_CODE ?? ''

test('without a session the pages are the demo, and the code opens the rest', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.goto('/')
  // the pages are there for the visitor; the way in is a link in the header
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByText(/demo: recorded answers; the code unlocks saving/)).toBeVisible()
  // the inventory shows what the owner made public; a save is what the code unlocks
  await page.getByRole('button', { name: 'My inventory' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Read a label' }).click()

  await page.getByRole('button', { name: 'Sign in with the code' }).click()
  const gate = page.getByRole('form', { name: 'Access code' })
  await expect(gate).toBeVisible()
  await gate.getByLabel('Access code').fill('not the code')
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(gate.getByRole('alert')).toContainText('not the access code')

  await gate.getByLabel('Access code').fill(code)
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toHaveCount(0)
  await expect(page.getByText(/demo: \d+ of \d+ calls today/)).toBeVisible()
  await page.getByRole('button', { name: 'My inventory' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)

  // the way out: the header's Sign out drops the page back to the demo, and it stays there
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0)
  await expect(page.getByText(/demo: recorded answers; the code unlocks saving/)).toBeVisible()
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

test('a public item shows the visitor neither its location nor its notes', async ({ page, playwright, baseURL }) => {
  test.skip(!code, 'the stack runs without a gate')
  // the owner, signed in on a context of its own, makes an item with both and marks it public
  const owner = await playwright.request.newContext({ baseURL })
  expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
  const name = `Shelf lamp ${Date.now().toString(36)}`
  const made = await owner.post('/api/items', {
    data: { name, item_type: 'desk lamp', location: 'garage shelf B', notes: 'paid 40 for it' },
  })
  expect(made.status()).toBe(201)
  const id = ((await made.json()) as { id: number }).id
  expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
  const mine = (await (await owner.get(`/api/items/${id}`)).json()) as { location: string; notes: string }
  expect(mine).toMatchObject({ location: 'garage shelf B', notes: 'paid 40 for it' })

  try {
    // the visitor's API answer carries neither
    const seen = await page.request.get(`/api/items/${id}`)
    expect(seen.status()).toBe(200)
    const body = await seen.text()
    expect(body).not.toContain('garage shelf B')
    expect(body).not.toContain('paid 40 for it')

    // and the dialog has no box for them
    await page.goto('/')
    await page.getByRole('button', { name: 'My inventory' }).click()
    await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
    const panel = page.getByRole('article', { name: `Item ${name}` })
    await expect(panel).toContainText('desk lamp')
    await expect(panel.getByText('Known faults')).toBeVisible()
    await expect(panel.getByText('Where it is (stays private)')).toHaveCount(0)
    await expect(panel.getByText('Notes (stay private)')).toHaveCount(0)
    await expect(panel).not.toContainText('garage shelf B')
    await expect(panel).not.toContainText('paid 40 for it')
  } finally {
    // the data volume outlives the run: the item leaves the public shelf
    await owner.post(`/api/items/${id}/public`, { data: { public: false } })
    await owner.dispose()
  }
})
