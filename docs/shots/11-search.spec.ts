import { expect, test } from './lib'

// Find a part, the planning tools: a laptop that needs its charger (the values from its
// adapter's label), a search for it, Plan the search (phrasings as Marketplace links, a pattern,
// words to skip), listings pasted back and ranked with no model call, Check fit on the best,
// and the message for the seller.

const LAPTOP = 'Laptop that lost its charger'
const TITLE = '65 W charger for the laptop'
const FITS = 'Orbital 65W laptop charger, 19.5V 3.34A, center positive barrel plug 4.5 x 3.0 mm. Works, light wear, comes with the power cord. $15, Astoria.'
const PARTS = 'Orbital charger OP065-19-333, for parts, cord frayed. $5'

test('Plan the search, the pattern, listings pasted back, Check fit, the seller', async ({ shots, page }) => {
  const request = page.request
  const made = await request.post('/api/items', { data: { item_type: 'laptop', name: LAPTOP, profile: 'power_adapter' } })
  expect(made.status()).toBe(201)
  const id = ((await made.json()) as { id: number }).id
  for (const [field, value] of Object.entries({
    output_voltage: '19.5',
    output_current: '3.33',
    polarity: 'center positive',
    plug_outer_diameter: '4.5',
    plug_inner_diameter: '3.0',
  })) {
    expect((await request.post(`/api/items/${id}/fields`, { data: { field, value } })).status()).toBe(200)
  }
  expect((await request.post('/api/searches', { data: { need_item_id: id, title: TITLE, max_price: 20 } })).status()).toBe(201)

  await page.goto('/#find')
  await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: new RegExp(TITLE) }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Search ${TITLE}` })
  const plan = panel.getByRole('region', { name: 'Plan the search' })
  await plan.getByRole('button', { name: 'Plan the search' }).click()
  const phrasings = plan.getByRole('list', { name: 'Search phrasings' })
  await expect(phrasings.getByRole('listitem').first()).toBeVisible({ timeout: 120_000 })
  await shots.show(plan)
  await shots.take('10-plan')
  await plan.getByLabel('Test the pattern').fill('charger 19.5 V / 3.34 A')
  await expect(plan.getByLabel('Pattern test')).toContainText('fits')
  await shots.show(plan.getByLabel('Words to match (pattern)'), 'center')
  await shots.take('11-pattern')

  const back = panel.getByRole('form', { name: 'Bring back listings' })
  await back.getByLabel(/Paste one or more listings/).fill(`${PARTS}\n---\n${FITS}`)
  await shots.show(back)
  await shots.take('12-bring-back')
  await back.getByRole('button', { name: 'Score 2 listings' }).click()
  const ranked = panel.getByRole('list', { name: 'Listings brought back, ranked' })
  const items = ranked.getByRole('listitem').filter({ has: page.locator('.listing-text') })
  await expect(items).toHaveCount(2)
  await shots.show(ranked)
  await shots.take('13-ranked')
  await items.nth(0).getByRole('button', { name: 'Check fit' }).click()
  const fit = items.nth(0).getByLabel(/Fit of listing/)
  await expect(fit).toContainText('documented candidate', { timeout: 120_000 })
  await shots.show(items.nth(0))
  await shots.take('14-fit')

  const candidate = panel.getByRole('region', { name: /Candidate Orbital 65W laptop charger/ })
  await candidate.getByRole('button', { name: 'Ask the seller' }).click()
  await expect(candidate.getByLabel('Message to the seller')).toBeVisible()
  await shots.show(candidate.getByLabel('Message to the seller'), 'center')
  await shots.take('15-ask-the-seller')
})
