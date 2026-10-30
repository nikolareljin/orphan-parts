import { deflateSync } from 'node:zlib'
import { expect, test, type APIRequestContext } from '@playwright/test'

function crc32(data: Buffer): number {
  let crc = 0xffffffff
  for (const byte of data) {
    crc ^= byte
    for (let i = 0; i < 8; i++) crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type: string, body: Buffer): Buffer {
  const length = Buffer.alloc(4)
  length.writeUInt32BE(body.length)
  const typed = Buffer.concat([Buffer.from(type, 'ascii'), body])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(typed))
  return Buffer.concat([length, typed, crc])
}

function greyPng(width = 64, height = 48): Buffer {
  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header.set([8, 2, 0, 0, 0], 8)
  const row = Buffer.alloc(1 + width * 3, 200)
  row[0] = 0
  const pixels = deflateSync(Buffer.concat(Array.from({ length: height }, () => row)))
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', pixels),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

// Names carry a run stamp: the local data volume keeps items between runs.
const stamp = Date.now().toString(36)

// Items made straight through the API, so each test starts from its own record.
async function createItem(request: APIRequestContext, spec: Record<string, unknown>): Promise<number> {
  const res = await request.post('/api/items', { data: spec })
  expect(res.status()).toBe(201)
  return ((await res.json()) as { id: number }).id
}

test('a reading is saved privately and shows up in the inventory to confirm', async ({ page }) => {
  await page.goto('/')
  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: greyPng() })
  await page.getByLabel('Find the label first with SAM 3.1, then read the crop').uncheck()
  await page.getByRole('button', { name: 'Read the label' }).click()
  await expect(page.getByRole('table', { name: 'Evidence' })).toBeVisible()

  const charger = `Desk charger ${stamp}`
  await page.getByLabel('Name').fill(charger)
  await page.getByRole('button', { name: 'Save privately' }).click()

  await expect(page.getByRole('heading', { name: 'My inventory' })).toBeVisible()
  const items = page.getByRole('table', { name: 'Items' })
  const row = items.getByRole('row', { name: charger })
  await expect(row).toContainText('Keep')
  await row.getByRole('button', { name: 'Open' }).click()

  const panel = page.getByRole('article', { name: `Item ${charger}` })
  await expect(panel).toContainText('laptop power adapter')
  // the photo the reading was made from is kept with the item, above the values to confirm
  const photo = panel.getByRole('img', { name: 'Item photo 1', exact: true })
  await expect(photo).toBeVisible()
  await expect.poll(() => photo.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await expect(panel.getByText(/\d+ to confirm/)).toBeVisible()
  const voltage = panel.getByRole('table', { name: 'Fields' }).getByRole('row', { name: /Output voltage/ })
  await expect(voltage).toContainText('19.5 V')
  await expect(voltage).toContainText('observed on a photo')
  await expect(voltage).toContainText('to confirm')
  await voltage.getByRole('button', { name: 'Accept' }).click()
  await expect(voltage).toContainText('accepted')
  await expect(voltage.getByRole('button', { name: 'Accept' })).toHaveCount(0)
})

test('intent, an owner value, a separated part and the history', async ({ page, request }) => {
  const webcam = `USB webcam ${stamp}`
  const id = await createItem(request, { item_type: webcam, condition: 'works' })
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  const items = page.getByRole('table', { name: 'Items' })
  await items.getByRole('row', { name: webcam }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${webcam}` })
  await expect(panel).toContainText('No photo kept with this item.')

  await panel.getByLabel('Intent').selectOption('sell')
  await expect(items.getByRole('row', { name: webcam })).toContainText('Sell')
  await expect(panel).toContainText('version 2')

  await panel.getByLabel('Field').fill('Resolution')
  await panel.getByLabel('Value').fill('1080p')
  await panel.getByRole('button', { name: 'Add field' }).click()
  const resolution = panel.getByRole('table', { name: 'Fields' }).getByRole('row', { name: /Resolution/ })
  await expect(resolution).toContainText('1080p')
  await expect(resolution).toContainText('stated by the owner')
  await expect(resolution).toContainText('accepted')

  const cable = `USB cable ${stamp}`
  await panel.getByLabel('Part', { exact: true }).fill(cable)
  await panel.getByLabel('Part condition').fill('frayed')
  await panel.getByRole('button', { name: 'Separate' }).click()
  await expect(panel.getByText(/Separated parts: #\d+/)).toBeVisible()
  await expect(items.getByRole('row', { name: cable })).toContainText(`part of #${id}`)

  await panel.getByRole('button', { name: 'History' }).click()
  const history = panel.getByRole('list', { name: 'History' })
  await expect(history).toContainText('created')
  await expect(history).toContainText('changed intent')
  await expect(history).toContainText('resolution set to 1080p (owner_reported)')
  await expect(history).toContainText(`component separated: ${cable}`)
})

test('deleting asks twice and then hides the item', async ({ page, request }) => {
  const phone = `broken phone ${stamp}`
  await createItem(request, { item_type: phone, intent: 'give' })
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  const items = page.getByRole('table', { name: 'Items' })
  await items.getByRole('row', { name: phone }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${phone}` })
  await panel.getByRole('button', { name: 'Delete', exact: true }).click()
  await panel.getByRole('button', { name: /Yes, delete item/ }).click()
  await expect(panel).toHaveCount(0)
  await expect(items.getByRole('row', { name: phone })).toHaveCount(0)
})

test('a write refused because the item changed in between reloads the item', async ({ page, request }) => {
  const lamp = `desk lamp ${stamp}`
  const id = await createItem(request, { item_type: lamp })
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name: lamp }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${lamp}` })
  await expect(panel).toContainText('version 1')

  // changed elsewhere while the page is open
  const elsewhere = await request.patch(`/api/items/${id}`, { data: { condition: 'flickers', version: 1 } })
  expect(elsewhere.status()).toBe(200)

  await panel.getByLabel('Intent').selectOption('give')
  await expect(panel.getByRole('alert')).toContainText('The item was reloaded')
  await expect(panel).toContainText('version 2')
  await expect(panel.getByRole('textbox', { name: 'Condition', exact: true })).toHaveValue('flickers')
  await expect(panel.getByLabel('Intent')).toHaveValue('keep')
})

test('a failed save keeps the reading on the page', async ({ page }) => {
  await page.route('**/api/items', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'the database is busy' }) })
      : route.continue(),
  )
  await page.goto('/')
  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: greyPng() })
  await page.getByLabel('Find the label first with SAM 3.1, then read the crop').uncheck()
  await page.getByRole('button', { name: 'Read the label' }).click()
  await expect(page.getByRole('table', { name: 'Evidence' })).toBeVisible()
  await page.getByRole('button', { name: 'Save privately' }).click()
  await expect(page.getByRole('alert')).toContainText('the database is busy')
  await expect(page.getByRole('table', { name: 'Evidence' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save privately' })).toBeVisible()
})
