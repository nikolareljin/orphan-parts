import { expect, test, type APIRequestContext } from '@playwright/test'

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

// a listing seen three days ago (UTC), still within the 14 days a candidate stays valid
const DAY_MS = 24 * 60 * 60 * 1000
const isoDay = (ms: number): string => new Date(ms).toISOString().slice(0, 10)
const SEEN = isoDay(Date.now() - 3 * DAY_MS)
const VALID_UNTIL = isoDay(Date.parse(SEEN) + 14 * DAY_MS)

const LISTING =
  'Orbital 65W laptop charger, 19.5V 3.34A, centre positive barrel plug 4.5 x 3.0 mm. Works, light wear, comes with the power cord. $15, Astoria.'

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

test('a search from an item hands off to Marketplace and a listing brought back is assessed', async ({ page, request }) => {
  test.slow() // the listing is read and assessed while five other workers keep the one backend busy
  const name = `Laptop needing adapter ${stamp}`
  const laptopId = await createLaptop(request, name)
  await page.goto('/')
  await page.getByRole('button', { name: 'Find a part' }).click()
  const form = page.getByRole('form', { name: 'New search' })
  await form.getByRole('combobox', { name: 'Needed by' }).selectOption(String(laptopId))
  await form.getByLabel('Looking for').fill(`65 W adapter ${stamp}`)
  await form.getByLabel('Max price').fill('25')
  await form.getByRole('button', { name: 'Start the search' }).click()

  const panel = page.getByRole('article', { name: `Search 65 W adapter ${stamp}` })
  await expect(panel.getByRole('link', { name: 'Search Marketplace' })).toHaveAttribute('href', /marketplace\/search\/\?query=65\+W\+adapter.*maxPrice=25/)
  await expect(panel).toContainText('power_adapter rules')

  const bring = panel.getByRole('form', { name: 'Bring a listing back' })
  await bring.getByRole('textbox', { name: 'Listing text' }).fill(LISTING)
  await bring.getByLabel('Seen on').fill(SEEN)
  await bring.getByRole('button', { name: 'Check fit' }).click()

  const candidate = panel.getByRole('region', { name: /Candidate Orbital 65W laptop charger/ })
  await expect(candidate).toContainText('documented candidate')
  await expect(candidate).toContainText(`seen ${SEEN}, valid until ${VALID_UNTIL}`)
  await expect(candidate).toContainText('15 USD')
  await expect(candidate.getByRole('status')).toContainText('Likely compatible')
  await expect(panel.getByRole('table', { name: 'Candidates' })).toContainText('Listing text')

  await candidate.getByRole('button', { name: 'Ask the seller' }).click()
  await expect(candidate.getByLabel('Message to the seller')).toHaveValue(/Is it still available/)
  await candidate.getByRole('button', { name: 'Withdraw' }).click()
  await expect(candidate).toContainText('withdrawn')
  await panel.getByRole('button', { name: 'Close search' }).click()
  await expect(panel).toContainText('closed')
  // a closed search takes no listing: the form is gone, not just refused on submit
  await expect(panel.getByRole('form', { name: 'Bring a listing back' })).toHaveCount(0)
})

test('a search from values written in rejects a listing that conflicts with them', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Find a part' }).click()
  const form = page.getByRole('form', { name: 'New search' })
  await form.getByRole('combobox', { name: 'Profile' }).selectOption('power_adapter')
  await form.getByLabel('Output voltage (V)').fill('12')
  await form.getByLabel('Looking for').fill(`12 V adapter ${stamp}`)
  await form.getByRole('button', { name: 'Start the search' }).click()

  const panel = page.getByRole('article', { name: `Search 12 V adapter ${stamp}` })
  await expect(panel.getByLabel('Needed values')).toContainText('output voltage 12')
  const bring = panel.getByRole('form', { name: 'Bring a listing back' })
  await bring.getByRole('textbox', { name: 'Listing text' }).fill(LISTING)
  await bring.getByRole('button', { name: 'Check fit' }).click()
  const candidate = panel.getByRole('region', { name: /Candidate Orbital 65W laptop charger/ })
  await expect(candidate).toContainText('rejected')
  await expect(candidate.getByRole('status')).toContainText('Conflict: does not fit')
})
