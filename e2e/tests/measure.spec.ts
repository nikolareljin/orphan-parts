import { deflateSync } from 'node:zlib'
import { expect, test, type APIRequestContext } from '@playwright/test'

// Marks land at exact pixels, so the canvas must show the photo at its own size.
test.use({ viewport: { width: 1280, height: 1800 } })

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

// The same synthetic photo the backend tests use: a ruler bar from x=100 to x=500 at y=400
// (400 px for 100 mm) and an opening whose inner edges sit at x=200 and x=340 on y=200.
function rulerPng(width = 640, height = 480): Buffer {
  const rows: Buffer[] = []
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 3, 200)
    row[0] = 0
    for (let x = 0; x < width; x++) {
      let ink = false
      if (y >= 398 && y <= 402 && x >= 100 && x <= 500) ink = true
      if (y >= 392 && y <= 408 && x >= 100 && x <= 500 && (x - 100) % 40 === 0) ink = true
      const ring = x >= 170 && x <= 370 && y >= 170 && y <= 230
      const hole = x >= 200 && x <= 340 && y >= 180 && y <= 220
      if (ring && !hole) ink = true
      if (ink) {
        row[1 + x * 3] = 20
        row[2 + x * 3] = 20
        row[3 + x * 3] = 20
      }
    }
    rows.push(row)
  }
  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header.set([8, 2, 0, 0, 0], 8)
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.concat(rows))),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

const stamp = Date.now().toString(36)

async function createItem(request: APIRequestContext, spec: Record<string, unknown>): Promise<number> {
  const res = await request.post('/api/items', { data: spec })
  expect(res.status()).toBe(201)
  return ((await res.json()) as { id: number }).id
}

async function openItem(page: import('@playwright/test').Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  return page.getByRole('article', { name: `Item ${name}` })
}

test('the opening of a vacuum tool is measured against a ruler and proposed on the item', async ({ page, request }) => {
  const name = `crevice tool ${stamp}`
  await createItem(request, { item_type: name, profile: 'vacuum_attachment' })
  const panel = await openItem(page, name)
  const measure = panel.getByRole('region', { name: 'Measure a feature' })
  await expect(measure.getByRole('combobox', { name: /^Feature/ })).toHaveValue('opening_inner_diameter')
  await expect(measure.getByText(/ruler lying across it/)).toBeVisible()

  await measure.getByLabel('Photo with a ruler or card in it').setInputFiles({ name: 'opening.png', mimeType: 'image/png', buffer: rulerPng() })
  await measure.getByLabel(/Taken straight on/).check()
  const canvas = measure.getByRole('img', { name: 'Photo to mark' })
  await expect(canvas).toBeVisible()
  await expect(measure.getByText('Mark end 1 of the known length')).toBeVisible()
  for (const [x, y] of [
    [100, 400],
    [500, 400],
    [200, 200],
    [340, 200],
  ]) {
    await canvas.click({ position: { x, y } })
  }
  await expect(measure.getByText('All marks placed')).toBeVisible()
  await measure.getByRole('button', { name: 'Measure', exact: true }).click()

  const status = measure.getByRole('status')
  await expect(status).toContainText(/35\.\d ± \d\.\d\d mm/)
  await expect(status).toContainText('two-point scale')
  await expect(status).toContainText('measure it with a caliper or ruler')
  const row = panel.getByRole('table', { name: 'Fields' }).getByRole('row', { name: /Opening inner diameter/ })
  await expect(row).toContainText('35.0 mm')
  await expect(row).toContainText('to confirm')
  await expect(measure.getByText('Past measurements (1)')).toBeVisible()
})

test('a capture that is not straight on is refused with the reason', async ({ page, request }) => {
  const name = `floor brush ${stamp}`
  await createItem(request, { item_type: name, profile: 'vacuum_attachment' })
  const panel = await openItem(page, name)
  const measure = panel.getByRole('region', { name: 'Measure a feature' })
  await measure.getByLabel('Photo with a ruler or card in it').setInputFiles({ name: 'opening.png', mimeType: 'image/png', buffer: rulerPng() })
  const canvas = measure.getByRole('img', { name: 'Photo to mark' })
  for (const [x, y] of [
    [100, 400],
    [500, 400],
    [200, 200],
    [340, 200],
  ]) {
    await canvas.click({ position: { x, y } })
  }
  await measure.getByRole('button', { name: 'Measure', exact: true }).click()
  const status = measure.getByRole('status')
  await expect(status).toContainText('Could not measure:')
  await expect(status).toContainText('view:')
  await expect(panel.getByRole('table', { name: 'Fields' })).toHaveCount(0)
})
