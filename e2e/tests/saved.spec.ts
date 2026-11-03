import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// What was asked for an item is shown as it was kept: the Decide cards with a reuse card's
// picture, the sell draft in Marketplace's fields, the give-away with how to post it, the price
// guidance and the search plan. The demo visitor reads them all without a refusal; opening the
// tabs asks no model, for the visitor or for the owner.

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const code = process.env.E2E_ACCESS_CODE ?? ''

// Every request the page sends that is not a read: opening a section must send none, since every
// call that asks a model is a POST (the backend is shared with other workers, so its spend
// counter cannot tell this page's calls apart).
function writes(page: Page): string[] {
  const sent: string[] = []
  page.on('request', (r) => {
    if (r.method() !== 'GET' && r.url().includes('/api/') && !r.url().endsWith('/api/access')) sent.push(`${r.method()} ${r.url()}`)
  })
  return sent
}

async function item(request: APIRequestContext, name: string, item_type: string, intent: string): Promise<number> {
  const res = await request.post('/api/items', { data: { name, item_type, intent, condition: 'works', faults: 'a scuff on the lid' } })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  expect((await request.post(`/api/items/${id}/fields`, { data: { field: 'ram', value: '8', unit: 'GB' } })).ok()).toBe(true)
  return id
}

// As the owner: a laptop to sell (draft, guidance, cards), a laptop to give away (give draft) and
// a laptop for a build (cards, the first reuse card drawn), each marked public, and a search with
// its plan for the build's laptop.
async function saved(owner: APIRequestContext) {
  const sell = await item(owner, `Sale laptop ${stamp}`, 'laptop', 'sell')
  const give = await item(owner, `Gift laptop ${stamp}`, 'laptop', 'give')
  const build = await item(owner, `Build laptop ${stamp}`, 'laptop', 'build')
  expect((await owner.put(`/api/items/${sell}/sell-details`, { data: { area: 'Astoria', lowest_price: 27.5, reason: `moving ${stamp}`, asking_price: 60 } })).ok()).toBe(true)
  expect((await owner.post(`/api/items/${sell}/drafts`, { data: { mode: 'sell' } })).status()).toBe(201)
  expect((await owner.post(`/api/items/${sell}/price`, { data: {} })).status()).toBe(201)
  expect((await owner.post(`/api/items/${give}/drafts`, { data: { mode: 'give' } })).status()).toBe(201)
  for (const id of [sell, give, build]) expect((await owner.post(`/api/items/${id}/scenarios`)).status()).toBe(201)
  const cards = (await (await owner.get(`/api/items/${build}/decide`)).json()) as { scenarios: { id: number } }
  expect((await owner.post(`/api/items/${build}/scenarios/${cards.scenarios.id}/reuse/0/picture`)).status()).toBe(201)
  expect((await owner.post(`/api/items/${build}/decision`, { data: { choice: 'keep_build', note: `owner note ${stamp}` } })).ok()).toBe(true)
  const search = await owner.post('/api/searches', { data: { need_item_id: build, profile: 'power_adapter', title: `65 W adapter ${stamp}`, max_price: 20 } })
  const sid = ((await search.json()) as { id: number }).id
  expect((await owner.post(`/api/searches/${sid}/plan`)).ok()).toBe(true)
  for (const id of [sell, give, build]) expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
  return { sell, give, build, sid }
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  return page.getByRole('article', { name: `Item ${name}` })
}

test.describe('the demo visitor', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('reads every saved result: the draft, the give-away, the cards with their picture and the plan', async ({ page, playwright, baseURL }) => {
    test.skip(!code, 'the stack runs without a gate')
    test.slow()
    const owner = await playwright.request.newContext({ baseURL })
    expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
    const ids = await saved(owner)
    const sent = writes(page)
    const refused: string[] = []
    page.on('response', (r) => {
      if (r.status() === 403) refused.push(r.url())
    })
    try {
      // the list marks what is saved and the plan chosen
      await page.goto('/')
      await page.getByRole('button', { name: 'My inventory' }).click()
      const row = page.getByRole('table', { name: 'Items' }).getByRole('row', { name: `Sale laptop ${stamp}` })
      await expect(row.getByRole('list', { name: /^Saved for/ })).toContainText('sell draft')
      await expect(row.getByRole('list', { name: /^Saved for/ })).toContainText('price guidance')

      // a sale: the whole listing in Marketplace's fields, the guidance; nothing private
      let panel = await openItem(page, `Sale laptop ${stamp}`)
      const handoff = panel.getByRole('region', { name: 'Marketplace handoff' })
      const fields = handoff.locator('dl[aria-label="Fields to paste"]')
      for (const label of ['Title', 'Price', 'Category', 'Condition', 'Description', 'Tags']) await expect(fields).toContainText(label)
      await expect(handoff.getByRole('textbox', { name: 'Draft text' })).not.toHaveValue('')
      await expect(handoff.getByRole('button', { name: 'Copy title' })).toBeEnabled()
      await expect(handoff).toContainText('Open Marketplace and choose Item for sale.')
      await expect(handoff.getByRole('checkbox').first()).toBeDisabled()
      await expect(handoff.getByRole('button', { name: 'Download photos' })).toHaveCount(0)
      await expect(panel.getByRole('button', { name: /Write (the|a new) draft/ })).toHaveCount(0)
      await expect(panel.getByText('Write a draft:')).toBeVisible()
      await expect(panel).not.toContainText('Astoria')
      await expect(panel).not.toContainText(`moving ${stamp}`)
      const value = panel.getByRole('region', { name: 'What is it worth?' })
      await expect(value.getByRole('table', { name: 'Quantities' })).toBeVisible()
      await expect(value.getByRole('button', { name: 'Get price guidance' })).toHaveCount(0)
      const decide = panel.getByRole('region', { name: 'Decide' })
      await expect(decide.getByRole('status', { name: 'Recommendation' })).toBeVisible()
      await expect(decide.getByRole('button', { name: 'Ask again' })).toHaveCount(0)
      await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()

      // a give-away: the free listing and how to post it
      panel = await openItem(page, `Gift laptop ${stamp}`)
      const gift = panel.getByRole('region', { name: 'Marketplace handoff' })
      await expect(gift).toContainText('Free')
      await expect(gift).toContainText('Set local pickup and your area.')
      await expect(gift.locator('dl[aria-label="Fields to paste"]')).toContainText('Description')
      await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()

      // a build: the cards, the reuse card's picture, the plan chosen without the owner's note
      panel = await openItem(page, `Build laptop ${stamp}`)
      const cards = panel.getByRole('region', { name: 'What to do with it' })
      for (const title of ['Keep and fix', 'Reuse it', 'Sell or give away']) await expect(cards.getByRole('article', { name: title })).toBeVisible()
      const reuse = cards.getByRole('article', { name: 'Reuse it' })
      await expect(reuse.getByRole('img', { name: /^Illustrative picture 1: / })).toBeVisible()
      await expect(cards.getByRole('button', { name: /^Choose this/ })).toHaveCount(0)
      await expect(panel.getByRole('status', { name: 'Decision made' })).toContainText('Keep and build')
      await expect(panel).not.toContainText(`owner note ${stamp}`)
      await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()

      // Find a part: the plan's phrasings, each a Marketplace link, and the pattern
      await page.getByRole('button', { name: 'Find a part' }).click()
      const title = `65 W adapter ${stamp}`
      await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: new RegExp(title) }).getByRole('button', { name: 'Open' }).click()
      const search = page.getByRole('article', { name: `Search ${title}` })
      const phrasings = search.getByRole('list', { name: 'Search phrasings' })
      await expect(phrasings.getByRole('link').first()).toHaveAttribute('href', /facebook\.com\/marketplace/)
      await expect(search.getByRole('button', { name: 'Plan again' })).toHaveCount(0)

      expect(refused).toEqual([])
      expect(sent).toEqual([])
    } finally {
      for (const id of [ids.sell, ids.give, ids.build]) await owner.post(`/api/items/${id}/public`, { data: { public: false } })
      await owner.dispose()
    }
  })
})

test('opening the tabs asks no model; asking again keeps the earlier answers', async ({ page, request }) => {
  test.slow()
  const name = `Kept laptop ${stamp}`
  const id = await item(request, name, 'laptop', 'sell')
  expect((await request.post(`/api/items/${id}/scenarios`)).status()).toBe(201)
  expect((await request.post(`/api/items/${id}/drafts`, { data: { mode: 'sell' } })).status()).toBe(201)
  const sent = writes(page)
  const panel = await openItem(page, name)
  const decide = panel.getByRole('region', { name: 'Decide' })
  await expect(decide.getByRole('status', { name: 'Recommendation' })).toBeVisible()
  await expect(panel.getByRole('region', { name: 'Marketplace handoff' })).toBeVisible()
  // nothing asked yet: what the step does and what it costs, beside its button
  await expect(panel.getByRole('region', { name: 'What is it worth?' }).getByRole('note', { name: 'Nothing asked yet' })).toContainText('$0.04')
  await expect(decide.getByRole('note', { name: 'Nothing asked yet' })).toContainText('Up to three ideas')
  expect(sent).toEqual([])

  // asking again adds new cards; the first stay under the earlier ones
  await decide.getByRole('button', { name: 'Ask again' }).click()
  await expect(decide).toContainText('version 2')
  const earlier = decide.locator('details.earlier').filter({ hasText: 'Earlier cards (1)' })
  await earlier.locator('summary').click()
  await earlier.getByRole('button', { name: /^Version 1/ }).click()
  await expect(decide).toContainText('version 1')
})
