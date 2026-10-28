import { deflateSync } from 'node:zlib'
import { expect, test } from '@playwright/test'

// A plain grey PNG built on the spot, so no binary lives in the repository. Fixture mode
// answers with the recorded readings and regions whatever the pixels are.
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

function greyPng(width = 640, height = 480): Buffer {
  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header.set([8, 2, 0, 0, 0], 8) // 8 bits, RGB, no compression flags, no filter, no interlace
  const row = Buffer.alloc(1 + width * 3, 200)
  row[0] = 0 // filter byte
  const pixels = deflateSync(Buffer.concat(Array.from({ length: height }, () => row)))
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', pixels),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

const findFirst = 'Find the label first with SAM 3.1, then read the crop'

test('a photo becomes an evidence table', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Orphan Parts Lens' })).toBeVisible()

  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: greyPng() })
  await expect(page.getByText('label.png')).toBeVisible()
  await page.getByLabel(findFirst).uncheck()
  await page.getByRole('button', { name: 'Read the label' }).click()

  const table = page.getByRole('table', { name: 'Evidence' })
  await expect(table).toBeVisible()
  await expect(page.getByRole('heading', { name: 'laptop power adapter' })).toBeVisible()

  const voltage = table.getByRole('row', { name: /Output voltage/ })
  await expect(voltage).toContainText('19.5 V')
  await expect(voltage).toContainText('97%')
  await expect(voltage).toContainText('photo')

  const part = table.getByRole('row', { name: /Part number/ })
  await expect(part).toContainText('OP065-19-333')
  await expect(part).toContainText('as printed: P/N OP065-19-333')

  await expect(page.getByText('recorded answer')).toBeVisible()
  await page.getByText('Label text').click()
  await expect(page.getByText('OUTPUT: 19.5V 3.33A 65W')).toBeVisible()
})

test('the label is found first and read from its crop', async ({ page }) => {
  // the recorded masks are decoded in pure Python, one concept after another: slow under load
  test.slow()
  await page.goto('/')
  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'adapter.png', mimeType: 'image/png', buffer: greyPng() })
  await expect(page.getByLabel(findFirst)).toBeChecked()
  await page.getByRole('button', { name: 'Read the label' }).click()

  const overlay = page.getByRole('img', { name: 'Photo with the found regions drawn over it' })
  await expect(overlay).toBeVisible({ timeout: 45_000 })
  const regions = page.getByRole('list', { name: 'Regions' })
  await expect(regions.getByRole('listitem')).toHaveCount(4)
  await expect(regions).toContainText('item')
  await expect(regions).toContainText('label')
  await expect(regions).toContainText('connector')
  await expect(regions).toContainText('88%')

  const table = page.getByRole('table', { name: 'Evidence' })
  await expect(table).toBeVisible()
  await expect(table.getByRole('row', { name: /Output voltage/ })).toContainText('label_crop')
})

test('a file that is not a photo is refused with the API message', async ({ page }) => {
  await page.goto('/')
  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not a photo') })
  await page.getByRole('button', { name: 'Read the label' }).click()

  await expect(page.getByRole('alert')).toContainText('the file is not an image')
  await expect(page.getByRole('table', { name: 'Evidence' })).toHaveCount(0)
})

test('photos past the limit are left out and the form says so', async ({ page }) => {
  await page.goto('/')
  const five = Array.from({ length: 5 }, (_, i) => ({
    name: `photo-${i + 1}.png`,
    mimeType: 'image/png',
    buffer: greyPng(8, 8),
  }))
  await page.getByLabel('Photos of the label').setInputFiles(five)

  await expect(page.getByText('Only the first 4 are used')).toBeVisible()
  await expect(page.getByRole('listitem')).toHaveCount(4)
  await expect(page.getByText('photo-5.png')).toHaveCount(0)
})

test('a photo over the size limit is refused before it is uploaded', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('12 MB each')).toBeVisible()
  const requests: string[] = []
  page.on('request', (r) => {
    if (r.url().includes('/api/')) requests.push(r.url())
  })
  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'huge.jpg', mimeType: 'image/jpeg', buffer: Buffer.alloc(13 * 1024 * 1024) })
  await page.getByRole('button', { name: 'Read the label' }).click()

  await expect(page.getByRole('alert')).toContainText('huge.jpg is 13.0 MB; the limit is 12 MB per photo')
  expect(requests.filter((u) => u.includes('/api/extract') || u.includes('/api/segment'))).toEqual([])
})

test('the service card reports fixture mode', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('fixture mode (no key, recorded responses)')).toBeVisible()
})
