import { expect, test } from '@playwright/test'

// These start without the session every other test carries: the two doors are the subject.
test.use({ storageState: { cookies: [], origins: [] } })

const code = process.env.E2E_ACCESS_CODE ?? ''

test('without a session the pages are the demo, and the code opens the rest', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.goto('/')
  // the pages are there for the visitor; the way in is a link in the header
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByText(/demo: recorded answers; the code unlocks saving/)).toBeVisible()
  await page.getByRole('button', { name: 'My inventory' }).click()
  await expect(page.getByRole('alert')).toContainText('demo: the code unlocks saving')

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
})

test('the API answers the demo visitor with recordings and refuses every write', async ({ request }) => {
  test.skip(!code, 'the stack runs without a gate')
  const refused = await request.get('/api/items')
  expect(refused.status()).toBe(403)
  expect(((await refused.json()) as { detail: string }).detail).toContain('demo: the code unlocks saving')
  const write = await request.post('/api/items', { data: { item_type: 'kettle' } })
  expect(write.status()).toBe(403)
  const open = await request.get('/api/version')
  expect(open.status()).toBe(200)
  const profiles = await request.get('/api/profiles')
  expect(profiles.status()).toBe(200)
  const access = (await (await request.get('/api/access')).json()) as { gated: boolean; granted: boolean; live: boolean }
  expect(access).toEqual({ gated: true, granted: false, live: false, token: '', expires_at: 0 })
})
