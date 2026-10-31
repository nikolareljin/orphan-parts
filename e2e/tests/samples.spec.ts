import { expect, test, type Page } from '@playwright/test'

// The demo visitor reads the demo set's photos: no file input anywhere, a gallery to pick
// from, and each reading the answer recorded for that very photo. Signed in, uploads are back.
test.use({ storageState: { cookies: [], origins: [] } })

const code = process.env.E2E_ACCESS_CODE ?? ''
const sampleLine = 'Recorded answer for this sample.'
const signInLine = 'Sign in with the access code to use this.'
const findFirst = 'Find the label in the photo first (SAM 3.1; helps with busy photos)'

async function open(page: Page, name: string) {
  await page.getByRole('button', { name, exact: true }).click()
}

test('signed out: no file input on any page, the samples instead', async ({ page, playwright, baseURL }) => {
  test.skip(!code, 'the stack runs without a gate')
  // a public item, made by the owner on a context of its own, for the item dialog's surfaces
  const owner = await playwright.request.newContext({ baseURL })
  expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
  const name = `Agitator ${Date.now().toString(36)}`
  const made = await owner.post('/api/items', { data: { name, item_type: 'blender agitator' } })
  const id = ((await made.json()) as { id: number }).id
  expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)

  try {
    await page.goto('/')
    await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()

    // Read a label: the gallery, grouped by item, and no upload
    await open(page, 'Read a label')
    await expect(page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })).toBeVisible()
    await expect(page.getByRole('checkbox')).not.toHaveCount(0)
    await expect(page.locator('input[type="file"]')).toHaveCount(0)

    // Inbox and Find: one line, no input
    await open(page, 'Inbox')
    await expect(page.getByText(signInLine)).toBeVisible()
    await expect(page.locator('input[type="file"]')).toHaveCount(0)
    await open(page, 'Find a part')
    await expect(page.getByText(signInLine)).toBeVisible()
    await expect(page.locator('input[type="file"]')).toHaveCount(0)

    // the item dialog: the voice note is the line, Measure offers the sample photos
    await open(page, 'My inventory')
    await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
    const panel = page.getByRole('article', { name: `Item ${name}` })
    await expect(panel.getByText('Voice note (WAV):')).toBeVisible()
    await expect(panel.getByRole('radio', { name: 'Frappé maker agitator, worn, photo 1 of 3' })).toBeVisible()
    await expect(panel.locator('input[type="file"]')).toHaveCount(0)
  } finally {
    await owner.post(`/api/items/${id}/public`, { data: { public: false } })
    await owner.dispose()
  }
})

test('signed out: several samples picked, each read with its own recorded answer', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  // what the server recorded for the single photo, to hold the page's answer against
  const alone = await page.request.post('/api/samples/read', { data: { sample_ids: ['agitator-head'], find_label: false } })
  expect(alone.status()).toBe(200)
  const own = ((await alone.json()) as { results: { extraction: { item_type: string } }[] }).results[0].extraction.item_type

  await page.goto('/')
  await open(page, 'Read a label')
  const gpu = page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })
  await gpu.getByRole('button', { name: 'Select all photos of this item' }).click()
  await expect(gpu.getByRole('checkbox')).toHaveCount(2)
  for (const box of await gpu.getByRole('checkbox').all()) await expect(box).toBeChecked()
  await page.getByRole('checkbox', { name: 'Frappé maker agitator, worn, photo 2 of 3' }).check()
  await expect(page.getByText('3 picked')).toBeVisible()
  await page.getByLabel(findFirst).uncheck()
  await page.getByRole('button', { name: 'Read the label' }).click()

  // one reading for the item's two photos, one for the single photo, side by side
  const group = page.getByRole('article', { name: 'Reading: EVGA GeForce 9800 GT graphics card, all 2 photos' })
  const single = page.getByRole('article', { name: 'Reading: Frappé maker agitator, worn, photo 2 of 3' })
  await expect(group).toBeVisible()
  await expect(single).toBeVisible()
  await expect(group.getByRole('note')).toHaveText(sampleLine)
  await expect(single.getByRole('note')).toHaveText(sampleLine)
  await expect(group.locator('.result .meta')).toContainText('2 photos')
  await expect(single.getByRole('heading', { name: own })).toBeVisible()
})

test('signed in: the file inputs are back', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  expect((await page.request.post('/api/access', { data: { code } })).ok()).toBe(true)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await open(page, 'Read a label')
  await expect(page.getByLabel('Photos of the label')).toBeVisible()
  await expect(page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })).toHaveCount(0)
  await open(page, 'Inbox')
  await page.getByText('Send a capture from this computer').click()
  await expect(page.locator('input[type="file"]')).not.toHaveCount(0)
})

test('access check failing: no file input on any upload page', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  // the tab never hears back from GET /api/access; unknown reads as the visitor
  await page.route('**/api/access', (route) => route.abort())
  await page.goto('/')
  await open(page, 'Read a label')
  await expect(page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
  await open(page, 'Inbox')
  await expect(page.getByText(signInLine)).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
  await open(page, 'Find a part')
  await expect(page.getByText(signInLine)).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
})

test('access check slow: the inputs wait for the answer, then show for the owner', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  expect((await page.request.post('/api/access', { data: { code } })).ok()).toBe(true)
  let release: () => void = () => undefined
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/access', async (route) => {
    await held
    await route.continue()
  })
  await page.goto('/')
  await open(page, 'Read a label')
  await expect(page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
  release()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await expect(page.getByLabel('Photos of the label')).toBeVisible()
})
