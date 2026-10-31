import { expect, test, type APIRequestContext } from '@playwright/test'

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

const PATTERN = 'OP-?065-?19-?333|19\\.5\\s*V.{0,20}3\\.3\\d?\\s*A'
const FITS = 'Orbital 65W laptop charger, 19.5V 3.34A, center positive barrel plug 4.5 x 3.0 mm. Works, light wear, comes with the power cord. $15, Astoria.'
const PARTS = 'Orbital charger OP065-19-333, for parts, cord frayed. $5'

async function createLaptop(request: APIRequestContext, name: string): Promise<number> {
  const res = await request.post('/api/items', { data: { item_type: 'laptop', name, profile: 'power_adapter' } })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  for (const [field, value] of Object.entries({
    output_voltage: '19.5',
    output_current: '3.33',
    polarity: 'center positive',
    plug_outer_diameter: '4.5',
    plug_inner_diameter: '3.0',
  })) {
    const added = await request.post(`/api/items/${id}/fields`, { data: { field, value } })
    expect(added.status()).toBe(200)
  }
  return id
}

test('a search plan gives phrasings and a pattern, and pasted listings come back ranked', async ({ page, request }) => {
  test.slow() // Check fit reads the listing while other workers keep the one backend busy
  const laptopId = await createLaptop(request, `Laptop for the plan ${stamp}`)
  const title = `65 W adapter plan ${stamp}`
  const created = await request.post('/api/searches', { data: { need_item_id: laptopId, title, max_price: 20 } })
  expect(created.status()).toBe(201)

  await page.goto('/')
  await page.getByRole('button', { name: 'Find a part' }).click()
  await page.getByRole('row', { name: new RegExp(title) }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Search ${title}` })
  const plan = panel.getByRole('region', { name: 'Plan the search' })
  await expect(plan).toContainText('no public search API')
  await expect(plan).toContainText('does not take regular expressions')

  await plan.getByRole('button', { name: 'Plan the search' }).click()
  const phrasings = plan.getByRole('list', { name: 'Search phrasings' })
  await expect(phrasings.getByRole('listitem')).toHaveCount(5)
  const link = phrasings.getByRole('link', { name: 'Orbital OP065-19-333' })
  await expect(link).toHaveAttribute('href', /marketplace\/search\/\?query=Orbital\+OP065-19-333&maxPrice=20$/)
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(plan.getByLabel('Match pattern (regular expression, any case)')).toHaveValue(PATTERN)
  await expect(plan.getByLabel('Exclusion words')).toContainText('for parts')

  // the live test box: the same engine as the ranking, the match highlighted
  await plan.getByLabel('Try the pattern on a line').fill('charger 19.5 V / 3.34 A')
  await expect(plan.getByLabel('Pattern test')).toContainText('fits')
  await expect(plan.getByLabel('Pattern test').locator('mark.hit-match')).toHaveText('19.5 V / 3.34 A')

  // a refused pattern is read out politely as it is typed, not as an alert
  const field = plan.getByLabel('Match pattern (regular expression, any case)')
  const live = plan.locator('.pattern-live[aria-live="polite"]')
  await field.fill('(?<=19.5 )V')
  await expect(live).toContainText('lookbehind')
  await expect(plan.locator('[role="alert"]')).toHaveCount(0)
  await field.fill(PATTERN)
  await expect(live).toBeEmpty()

  // a word added is shown as the backend kept it, with a remove target of 24 px at least
  const words = plan.getByLabel('Exclusion words')
  await words.getByLabel('Add an exclusion word').fill('worn   out')
  await words.getByLabel('Add an exclusion word').press('Enter')
  const remove = words.getByRole('button', { name: 'Remove worn out', exact: true })
  await expect(remove).toBeVisible()
  await expect(words.locator('.chip').filter({ hasText: 'worn' })).toHaveText(/^worn out×$/)
  const target = await remove.boundingBox()
  expect(target?.width ?? 0).toBeGreaterThanOrEqual(24)
  expect(target?.height ?? 0).toBeGreaterThanOrEqual(24)
  await remove.click()
  await expect(words.locator('.chip').filter({ hasText: 'worn' })).toHaveCount(0)

  const back = panel.getByRole('form', { name: 'Bring back listings' })
  await back.getByLabel(/Listings, as pasted/).fill(`${PARTS}\n---\n${FITS}`)
  await back.getByRole('button', { name: 'Score 2 listings' }).click()

  const ranked = panel.getByRole('list', { name: 'Listings brought back, ranked' })
  const items = ranked.getByRole('listitem').filter({ has: page.locator('.listing-text') })
  await expect(items).toHaveCount(2)
  await expect(items.nth(0)).toContainText('fits')
  await expect(items.nth(0).locator('mark.hit-match')).toHaveText('19.5V 3.34A')
  await expect(items.nth(1)).toContainText('does not fit')
  await expect(items.nth(1)).toContainText('says "for parts"')
  await expect(items.nth(1).locator('mark.hit-excluded')).toHaveText(['for parts', 'frayed'])

  await items.nth(0).getByRole('button', { name: 'Check fit' }).click()
  const fit = items.nth(0).getByLabel(/Fit of listing/)
  await expect(fit).toContainText('documented candidate')
  await expect(panel.getByRole('table', { name: 'Candidates' })).toContainText('Orbital 65W laptop charger')

  // on a phone the day seen gets its own line, not squeezed beside the button
  await page.setViewportSize({ width: 390, height: 844 })
  const day = await back.getByLabel('Seen on').boundingBox()
  const score = await back.getByRole('button', { name: /Score/ }).boundingBox()
  expect(day?.width ?? 0).toBeGreaterThanOrEqual(200)
  expect(score?.y ?? 0).toBeGreaterThanOrEqual((day?.y ?? 0) + (day?.height ?? 0))
})
