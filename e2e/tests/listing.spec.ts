import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const stamp = Date.now().toString(36)

// A short WAV of silence: fixture mode answers with the recorded transcript whatever is heard.
function silenceWav(seconds = 1, rate = 8000): Buffer {
  const frames = seconds * rate
  const header = Buffer.alloc(44)
  header.write('RIFF', 0)
  header.writeUInt32LE(36 + frames, 4)
  header.write('WAVE', 8)
  header.write('fmt ', 12)
  header.writeUInt32LE(16, 16)
  header.writeUInt16LE(1, 20) // PCM
  header.writeUInt16LE(1, 22) // mono
  header.writeUInt32LE(rate, 24)
  header.writeUInt32LE(rate, 28)
  header.writeUInt16LE(1, 32)
  header.writeUInt16LE(8, 34)
  header.write('data', 36)
  header.writeUInt32LE(frames, 40)
  return Buffer.concat([header, Buffer.alloc(frames, 0x80)])
}

async function createAdapter(request: APIRequestContext, name: string, confirm = true): Promise<number> {
  const res = await request.post('/api/items', {
    data: { item_type: 'laptop power adapter', name, faults: 'frayed sleeve near the plug', condition: 'scuffed' },
  })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  const field = await request.post(`/api/items/${id}/fields`, { data: { field: 'output_voltage', value: '19.5', unit: 'V' } })
  expect(field.status()).toBe(200)
  if (confirm) {
    const pol = await request.post(`/api/items/${id}/fields`, { data: { field: 'polarity', value: 'center positive' } })
    expect(pol.status()).toBe(200)
  }
  return id
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${name}` })
  return { panel, listing: panel.getByRole('region', { name: 'Prepare to sell or give away' }) }
}

test.use({ permissions: ['clipboard-read', 'clipboard-write'] })

test('tell us more, then the Marketplace handoff: fields to copy, the create page, listed and sold', async ({ page, request }) => {
  test.slow() // a draft, a checklist and outcomes, each a write, with five other workers on the backend
  const name = `Orbital charger ${stamp}`
  await createAdapter(request, name)
  const { listing } = await openItem(page, name)
  await expect(listing).toContainText('No public API posts a personal Marketplace listing')
  const form = listing.getByRole('form', { name: 'Tell us more' })
  await form.getByLabel('Condition in your words').fill('works, scuffed case')
  await form.getByLabel('Power cord').check()
  await form.getByLabel('Area').fill('12 Oak Street')
  await form.getByRole('button', { name: 'Save details' }).click()
  await expect(listing.getByRole('alert')).toContainText('not a street address')
  await form.getByLabel('Area').fill('Astoria')
  await form.getByLabel('Asking price (USD)').fill('$15')
  await form.getByLabel('Lowest you would take (private)').fill('11')
  await form.getByLabel('Your reason (private)').fill('moving to Denver')
  await form.getByRole('button', { name: 'Write the draft' }).click()

  const draft = listing.getByRole('status')
  await expect(draft).toContainText('Marketplace handoff')
  await expect(draft).toContainText('recorded answer')
  const text = draft.getByLabel('Draft text')
  await expect(text).toHaveValue(/Known faults: frayed sleeve near the plug/)
  await expect(text).toHaveValue(/Included: power cord/)
  await expect(text).toHaveValue(/Local pickup in Astoria\.$/)
  await expect(text).not.toHaveValue(/Denver|11/)
  const fields = draft.getByLabel('Fields to paste')
  await expect(fields).toContainText('$15')
  await expect(fields).toContainText('your asking price')
  await expect(draft.getByLabel('Category', { exact: true })).toHaveValue('Electronics > Computers')
  await expect(draft.getByLabel('Condition', { exact: true })).toHaveValue('Used - Good')
  await expect(form).toContainText('details v1 saved')

  await draft.getByRole('button', { name: 'Copy title' }).click()
  await expect(draft.getByRole('button', { name: 'Copy title' })).toHaveText('Copied')
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^Orbital 65 W laptop power adapter/)
  await draft.getByRole('button', { name: 'Copy price' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('15')
  await draft.getByLabel('Condition', { exact: true }).selectOption('Used - Fair')
  await draft.getByRole('button', { name: 'Copy condition' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('Used - Fair')
  await draft.getByRole('button', { name: 'Copy description' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('Known faults: frayed sleeve near the plug')

  const open = draft.getByRole('link', { name: 'Open Marketplace' })
  await expect(open).toHaveAttribute('href', 'https://www.facebook.com/marketplace/create/item')
  await expect(open).toHaveAttribute('target', '_blank')
  await expect(draft).toContainText('Check the preview, then publish.')
  await expect(draft).toContainText('required step(s) left')

  // the tick is a write; wait for it to land before the page reloads
  await Promise.all([
    page.waitForResponse((res) => res.url().includes('/checklist') && res.ok()),
    draft.getByLabel(/Clean the outside/).check(),
  ])
  await page.reload()
  const again = await openItem(page, name)
  const kept = again.listing.getByRole('status')
  await expect(kept.getByLabel(/Clean the outside/)).toBeChecked()
  await expect(again.listing.getByLabel('Area', { exact: true })).toHaveValue('Astoria')

  const after = kept.getByLabel('After posting')
  await after.getByLabel('Listing address (optional)').fill('https://www.facebook.com/marketplace/item/1234567890/')
  await after.getByRole('button', { name: 'Mark as listed' }).click()
  await expect(after).toContainText('listed on')
  await after.getByLabel('Price (USD)').fill('13')
  await after.getByRole('button', { name: 'Mark as sold' }).click()
  await expect(after).toContainText('sold on')
  await expect(after).toContainText('at $13')
})

test('a give-away is free under Free Stuff, worded for pickup, with the data steps', async ({ page, request }) => {
  const name = `Old tablet ${stamp}`
  await createAdapter(request, name)
  const { listing } = await openItem(page, name)
  const form = listing.getByRole('form', { name: 'Tell us more' })
  await form.getByLabel('Give away').check()
  await expect(form.getByLabel('Asking price (USD)')).toHaveCount(0)
  await form.getByLabel('Accounts or files').selectOption('wiped')
  await form.getByLabel('Area').fill('11105')
  await form.getByRole('button', { name: 'Write the draft' }).click()

  const draft = listing.getByRole('status')
  await expect(draft).toContainText('Free: Orbital 65 W laptop power adapter')
  await expect(draft).toContainText('Free (0)')
  await expect(draft.getByLabel('Category', { exact: true })).toHaveValue('Free Stuff')
  await expect(draft).toContainText('Could be useful for: Spare charger')
  await expect(draft.getByLabel('Draft text')).toHaveValue(/Data: signed out of every account and wiped\./)
  await expect(draft.getByLabel('Draft text')).toHaveValue(/Free\. Local pickup in 11105\.$/)
  await expect(draft).toContainText('Your data')
  await expect(draft.getByLabel(/Factory reset/)).toBeVisible()
  await draft.getByRole('button', { name: 'Mark as given' }).click()
  await expect(draft.getByLabel('After posting')).toContainText('given on')
})

test('a voice note is transcribed and kept as the owner’s words', async ({ page, request }) => {
  const name = `Noted adapter ${stamp}`
  await createAdapter(request, name)
  const { panel, listing } = await openItem(page, name)
  await listing.getByLabel('Voice note (WAV)').setInputFiles({ name: 'note.wav', mimeType: 'audio/wav', buffer: silenceWav() })
  await expect(listing.getByText(/Heard and kept as your words/)).toContainText('Case is scuffed')
  const row = panel.getByRole('table', { name: 'Fields' }).getByRole('row', { name: /Condition notes/ })
  await expect(row).toContainText('Case is scuffed')
  await expect(row).toContainText('stated by the owner')
  await expect(row).toContainText('accepted')
})
