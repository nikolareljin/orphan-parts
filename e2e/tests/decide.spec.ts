import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

async function createLaptop(request: APIRequestContext, name: string): Promise<number> {
  const res = await request.post('/api/items', {
    data: { item_type: 'laptop', name, condition: 'scuffed lid', faults: 'battery holds an hour', tests_done: 'boots to the desktop' },
  })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  const field = await request.post(`/api/items/${id}/fields`, { data: { field: 'ram', value: '8', unit: 'GB' } })
  expect(field.status()).toBe(200)
  return id
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${name}` })
  return { panel, decide: panel.getByRole('region', { name: 'Decide' }) }
}

test('the decide panel gathers the rows, asks for ideas, and keeps the choice on the item', async ({ page, request }) => {
  const name = `Old laptop ${stamp}`
  await createLaptop(request, name)
  const { panel, decide } = await openItem(page, name)

  // the rules first: the templates a laptop fills, what is known, what is not asked yet
  await expect(decide).toContainText('laptop · 1 of 1 value accepted')
  await expect(decide).toContainText('Not asked yet.')
  await expect(decide).toContainText('Homework workstation (laptop)')
  await expect(decide).toContainText('No open search from this item.')
  await expect(decide.getByRole('button', { name: 'See picture controls' })).toBeVisible()

  // the model's proposals, from the recorded answer, labeled as proposals
  await decide.getByRole('button', { name: 'Ask for ideas' }).click()
  const ideas = decide.getByRole('status', { name: /Ideas/ })
  await expect(ideas).toContainText("The model's proposals")
  await expect(ideas).toContainText('recorded answer')
  const list = ideas.getByRole('list', { name: 'Ideas' })
  await expect(list.getByRole('listitem')).toHaveCount(3)
  await expect(list).toContainText('Homework workstation with a bigger screen')
  await expect(list).toContainText('Needs: an external monitor')
  await expect(list).toContainText('low effort')

  // a guidance written on the Value panel is read into the worth row at once
  await panel.getByRole('region', { name: 'What is it worth?' }).getByRole('button', { name: 'Price guidance' }).click()
  await expect(decide).toContainText(/about \d/)
  await expect(decide).not.toContainText('Not asked yet.')

  // the choice sets the intent and is kept with its note and date
  await decide.getByLabel('Note').fill('worth a listing')
  await decide.getByRole('button', { name: 'Sell', exact: true }).click()
  const decided = decide.getByRole('status', { name: 'Decision made' })
  await expect(decided).toContainText('Sell')
  await expect(decided).toContainText('worth a listing')
  await expect(panel.getByLabel('Intent')).toHaveValue('sell')
  await expect(panel.getByRole('region', { name: 'Prepare to sell or give away' }).getByLabel('Sell')).toBeChecked()

  // the history has the line, and the panel reads it back after a reload
  await panel.getByRole('button', { name: 'History' }).click()
  await expect(panel.getByRole('list', { name: 'History' })).toContainText('decided: sell: worth a listing')
  await page.reload()
  const again = await openItem(page, name)
  await expect(again.decide).toContainText('Decided:')
  await expect(again.decide).toContainText('worth a listing')
})

test('what to do with it: three cards for the profile, and a card chosen leads on', async ({ page, request }) => {
  const name = `Scenario laptop ${stamp}`
  await createLaptop(request, name)
  const { panel, decide } = await openItem(page, name)

  await decide.getByRole('button', { name: 'What should I do with it?' }).click()
  const cards = decide.getByRole('region', { name: 'What to do with it' })
  await expect(cards).toContainText("The model's scenarios")
  await expect(cards).toContainText('recorded answer')
  await expect(cards.getByRole('status', { name: 'Recommendation' })).toContainText('Recommended: Reuse it.')
  const fix = cards.getByRole('article', { name: 'Keep and fix' })
  const reuse = cards.getByRole('article', { name: 'Reuse it' })
  const sell = cards.getByRole('article', { name: 'Sell or give away' })
  await expect(fix.getByRole('list', { name: 'Steps' }).getByRole('listitem')).toHaveCount(4)
  await expect(fix).toContainText('easy for you')
  await expect(reuse).toContainText('recommended')
  await expect(reuse.getByRole('list', { name: 'Reuse scenarios' }).getByRole('listitem')).toHaveCount(2)
  await expect(reuse).toContainText('With what you have: monitor')
  await expect(sell.getByRole('button', { name: 'Get price guidance' })).toBeVisible()

  // the sell card asks the price route; the figure shows on the card
  await sell.getByRole('button', { name: 'Get price guidance' }).click()
  await expect(sell).toContainText(/about \d/)

  // keep and fix: the choice is kept, and the steps land in the notes
  await fix.getByRole('button', { name: 'Choose this' }).click()
  await expect(decide.getByRole('status', { name: 'Decision made' })).toContainText('Keep and fix')
  await expect(fix).toContainText('chosen')
  await expect(panel.getByLabel('Notes (stay private)')).toHaveValue(/Repair plan \(scenarios v1/)
  await expect(cards).toContainText('item changed since')
})

test('the decision rows fit a phone dialog', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const name = `Phone laptop ${stamp}`
  await createLaptop(request, name)
  const { decide } = await openItem(page, name)
  await expect(decide).toContainText('Homework workstation (laptop)')
  await decide.getByRole('button', { name: 'What should I do with it?' }).click()
  await expect(decide.getByRole('article', { name: 'Sell or give away' })).toBeVisible()
  const sizes = await decide.evaluate((el) => ({ width: el.clientWidth, scroll: el.scrollWidth }))
  expect(sizes.scroll).toBeLessThanOrEqual(sizes.width)
  await decide.getByRole('link', { name: 'Find a part', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page).toHaveURL(/#find$/)
})
