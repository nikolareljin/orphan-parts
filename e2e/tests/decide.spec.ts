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
  await expect(decide).toContainText('Picture: coming.')

  // the model's proposals, from the recorded answer, labelled as proposals
  await decide.getByRole('button', { name: 'Ask for ideas' }).click()
  const ideas = decide.getByRole('status', { name: /Ideas/ })
  await expect(ideas).toContainText("The model's proposals")
  await expect(ideas).toContainText('recorded answer')
  const list = ideas.getByRole('list', { name: 'Ideas' })
  await expect(list.getByRole('listitem')).toHaveCount(3)
  await expect(list).toContainText('Homework workstation with a bigger screen')
  await expect(list).toContainText('Needs: an external monitor')
  await expect(list).toContainText('low effort')

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
