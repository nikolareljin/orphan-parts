import { deflateSync } from 'node:zlib'
import { expect, test } from '@playwright/test'

// A 1 by 1 pixel PNG built on the spot, so no binary lives in the repository. Fixture mode
// answers with the recorded reading whatever the pixels are.
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

function tinyPng(): Buffer {
  const header = Buffer.alloc(13)
  header.writeUInt32BE(1, 0) // width
  header.writeUInt32BE(1, 4) // height
  header.set([8, 2, 0, 0, 0], 8) // 8 bits, RGB, no compression flags, no filter, no interlace
  const pixels = deflateSync(Buffer.from([0, 200, 200, 200])) // filter byte, then one grey pixel
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', pixels),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

test('a photo becomes an evidence table', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Orphan Parts Lens' })).toBeVisible()

  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: tinyPng() })
  await expect(page.getByText('label.png')).toBeVisible()
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
    buffer: tinyPng(),
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
    if (r.url().includes('/api/extract')) requests.push(r.url())
  })
  await page
    .getByLabel('Photos of the label')
    .setInputFiles({ name: 'huge.jpg', mimeType: 'image/jpeg', buffer: Buffer.alloc(13 * 1024 * 1024) })
  await page.getByRole('button', { name: 'Read the label' }).click()

  await expect(page.getByRole('alert')).toContainText('huge.jpg is 13.0 MB; the limit is 12 MB per photo')
  expect(requests).toEqual([])
})

test('the service card reports fixture mode', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('fixture mode (no key, recorded responses)')).toBeVisible()
})
