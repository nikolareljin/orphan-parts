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

test('a sale draft keeps confirmed facts, discloses the faults, and its checklist is kept', async ({ page, request }) => {
  const name = `Orbital charger ${stamp}`
  await createAdapter(request, name)
  const { listing } = await openItem(page, name)
  await listing.getByLabel('Asking price').fill('$15')
  await listing.getByLabel('Pickup').fill('Astoria, evenings')
  await listing.getByRole('button', { name: 'Write the draft' }).click()

  const draft = listing.getByRole('status')
  await expect(draft).toContainText('Orbital 65 W laptop power adapter')
  await expect(draft).toContainText('recorded answer')
  const text = draft.getByLabel('Draft text')
  await expect(text).toHaveValue(/Known faults: frayed sleeve near the plug/)
  await expect(text).toHaveValue(/Not tested; sold as is\./)
  await expect(text).toHaveValue(/Price: \$15\nPickup: Astoria, evenings$/)
  await expect(draft.getByRole('list', { name: 'Facts' })).toContainText('from output voltage')
  await expect(draft.getByRole('list', { name: 'Before posting' })).toContainText('rested on nothing confirmed')
  await expect(draft).toContainText('required step(s) left')
  await expect(draft.getByRole('link', { name: 'Open Marketplace' })).toHaveAttribute('href', /facebook\.com\/marketplace\/create\/item/)

  await draft.getByLabel(/Clean the outside/).check()
  await page.reload()
  const again = await openItem(page, name)
  await expect(again.listing.getByRole('status').getByLabel(/Clean the outside/)).toBeChecked()
})

test('a give-away draft is free, lists uses and adds the data steps', async ({ page, request }) => {
  const name = `Old tablet ${stamp}`
  await createAdapter(request, name)
  const { listing } = await openItem(page, name)
  await listing.getByLabel('Give away').check()
  await listing.getByLabel(/Stores accounts or files/).check()
  await listing.getByLabel('Pickup').fill('porch')
  await listing.getByRole('button', { name: 'Write the draft' }).click()

  const draft = listing.getByRole('status')
  await expect(draft).toContainText('Free: Orbital 65 W laptop power adapter')
  await expect(draft).toContainText('Could be useful for: Spare charger')
  await expect(draft.getByLabel('Draft text')).toHaveValue(/Free to collect\. Pickup: porch$/)
  await expect(draft).toContainText('Your data')
  await expect(draft.getByLabel(/Factory reset/)).toBeVisible()
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
