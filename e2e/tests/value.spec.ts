import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// a random tail too: two spec files loaded in the same millisecond must not share a name
const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

async function createAdapter(request: APIRequestContext, name: string): Promise<number> {
  const res = await request.post('/api/items', {
    data: { item_type: 'laptop power adapter', name, faults: 'frayed sleeve near the plug', condition: 'scuffed' },
  })
  expect(res.status()).toBe(201)
  return ((await res.json()) as { id: number }).id
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${name}` })
  return { panel, value: panel.getByRole('region', { name: 'What is it worth?' }) }
}

test('price guidance keeps the four figures apart and backs every comparable with a page', async ({ page, request }) => {
  const name = `Priced charger ${stamp}`
  await createAdapter(request, name)
  const { value } = await openItem(page, name)
  await value.getByRole('button', { name: 'Price guidance' }).click()

  const guide = value.getByRole('status')
  await expect(guide).toContainText('recorded answer')
  await expect(guide).toContainText('1 search')
  await expect(guide).toContainText('4 backed comparables, 1 line left out')
  const table = guide.getByRole('table', { name: 'Quantities' })
  await expect(table.getByRole('row', { name: /asking prices seen/ })).toContainText('12.50 USD to 22 USD')
  await expect(table.getByRole('row', { name: /sold prices seen/ })).toContainText('15 USD')
  await expect(table.getByRole('row', { name: /sales you reported/ })).toContainText('none')
  await expect(table.getByRole('row', { name: /the model's estimate/ })).toContainText('labelled as such')
  await expect(guide.getByRole('list', { name: 'Ways to price' })).toContainText('Quick sale 12 USD')
  const comparables = guide.getByRole('list', { name: 'Comparables' })
  await expect(comparables.getByRole('link').first()).toHaveAttribute('href', /example\.org\/listings\//)
  await expect(comparables).not.toContainText('forum')
  await expect(guide.getByRole('list', { name: 'Caveats' })).toContainText('rest on no search result')
})

test('a sale the owner records counts under its own figure', async ({ page, request }) => {
  const name = `Reported adapter ${stamp}`
  await createAdapter(request, name)
  const { value } = await openItem(page, name)
  await value.getByLabel(/^Price \(USD\)/).fill('16')
  await value.getByLabel('Sold on').fill('2026-09-30')
  await value.getByLabel('Note').fill('a friend')
  await value.getByRole('button', { name: 'Record' }).click()
  await expect(value.getByRole('list', { name: 'Sales you reported' })).toContainText('16 USD on 2026-09-30')

  await value.getByRole('button', { name: 'Price guidance' }).click()
  const row = value.getByRole('status').getByRole('table', { name: 'Quantities' }).getByRole('row', { name: /sales you reported/ })
  await expect(row).toContainText('16 USD')
})
