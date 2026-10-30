import { expect, test } from '@playwright/test'

// These start without the session every other test carries: the gate itself is the subject.
test.use({ storageState: { cookies: [], origins: [] } })

const code = process.env.E2E_ACCESS_CODE ?? ''

test('without a session the pages are behind the access code, and the right code opens them', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.goto('/')
  const gate = page.getByRole('form', { name: 'Access code' })
  await expect(gate).toBeVisible()
  await expect(page.getByRole('button', { name: 'My inventory' })).toHaveCount(0)

  await gate.getByLabel('Access code').fill('not the code')
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(gate.getByRole('alert')).toContainText('not the access code')

  await gate.getByLabel('Access code').fill(code)
  await gate.getByRole('button', { name: 'Enter' }).click()
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByText(/demo: \d+ of \d+ calls today/)).toBeVisible()
})

test('a request without a session is refused by the API', async ({ request }) => {
  test.skip(!code, 'the stack runs without a gate')
  const res = await request.get('/api/items')
  expect(res.status()).toBe(401)
  const open = await request.get('/api/version')
  expect(open.status()).toBe(200)
})
