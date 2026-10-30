import { deflateSync } from 'node:zlib'
import { expect, test, type APIRequestContext } from '@playwright/test'

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

// A small PNG and a short WAV, made here; the fixtures answer regardless of their content.
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
function png(width = 64, height = 48): Buffer {
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
function wav(seconds = 1): Buffer {
  const rate = 8000
  const data = Buffer.alloc(rate * seconds, 0x80)
  const header = Buffer.alloc(44)
  header.write('RIFF', 0)
  header.writeUInt32LE(36 + data.length, 4)
  header.write('WAVE', 8)
  header.write('fmt ', 12)
  header.writeUInt32LE(16, 16)
  header.writeUInt16LE(1, 20)
  header.writeUInt16LE(1, 22)
  header.writeUInt32LE(rate, 24)
  header.writeUInt32LE(rate, 28)
  header.writeUInt16LE(1, 32)
  header.writeUInt16LE(8, 34)
  header.write('data', 36)
  header.writeUInt32LE(data.length, 40)
  return Buffer.concat([header, data])
}
function mp4(): Buffer {
  const head = Buffer.alloc(16)
  head.writeUInt32BE(16, 0)
  head.write('ftyp', 4)
  head.write('isom', 8)
  head.writeUInt32BE(512, 12)
  return Buffer.concat([head, Buffer.alloc(512)])
}

// What the tests send is removed again: the inbox is the owner's, and a stub clip with no
// video track would otherwise stay there as a capture that cannot play.
const created: number[] = []
test.afterEach(async ({ request }) => {
  for (const id of created.splice(0)) await request.delete(`/api/captures/${id}`)
})

async function sendCapture(request: APIRequestContext, note: string): Promise<number> {
  const res = await request.post('/api/captures', {
    multipart: {
      photos: { name: 'a.png', mimeType: 'image/png', buffer: png() },
      clip: { name: 'clip.mp4', mimeType: 'video/mp4', buffer: mp4() },
      audio: { name: 'note.wav', mimeType: 'audio/wav', buffer: wav() },
      request: JSON.stringify({ note, name: `Captured adapter ${stamp}`, find_label: false }),
    },
  })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  created.push(id)
  return id
}

test('a capture from the phone is listed, read into an item and opened', async ({ page, request }) => {
  const id = await sendCapture(request, `from the drawer ${stamp}`)
  await page.goto('/')
  await page.getByRole('button', { name: 'Inbox' }).click()
  const card = page.getByRole('listitem').filter({ hasText: `Capture #${id}` })
  await expect(card).toContainText('received, not read yet')
  await expect(card).toContainText('1 photo, a clip of 1 KB, a note of 1 s')
  await expect(card).toContainText(`from the drawer ${stamp}`)
  await expect(card.getByRole('img', { name: `Capture ${id}, photo 1` })).toBeVisible()
  await card.getByRole('button', { name: 'Read it' }).click()
  await expect(card).toContainText('read into an item')
  await expect(card).toContainText('read by')
  await card.getByRole('button', { name: /Open item #\d+/ }).click()
  await expect(page.getByRole('dialog')).toContainText(`Captured adapter ${stamp}`)
  const photo = page.getByRole('dialog').getByRole('img', { name: 'Item photo 1', exact: true })
  await expect(photo).toBeVisible()
  await expect.poll(() => photo.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
})

test('a capture is sent from the computer through the form', async ({ page, request }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Inbox' }).click()
  const form = page.getByRole('form', { name: 'Send a capture' })
  await form.getByText('Send a capture from this computer').click()
  await form.getByLabel('Photos').setInputFiles({ name: 'label.png', mimeType: 'image/png', buffer: png() })
  await form.getByLabel('A short video (optional)').setInputFiles({ name: 'clip.mp4', mimeType: 'video/mp4', buffer: mp4() })
  await form.getByLabel('Name (optional)').fill(`From the desk ${stamp}`)
  await form.getByLabel('What you know (optional)').fill('an adapter from the desk drawer')
  await form.getByRole('button', { name: 'Send' }).click()
  await expect(form).toContainText(/Sent as capture #\d+/)
  const card = page.getByRole('listitem').filter({ hasText: `From the desk ${stamp}` })
  await expect(card).toContainText('1 photo, a clip of 1 KB')
  const id = Number((await card.innerText()).match(/Capture #(\d+)/)?.[1])
  created.push(id)
  expect((await request.get(`/api/captures/${id}`)).status()).toBe(200)
})

test('a capture is deleted from the inbox', async ({ page, request }) => {
  const id = await sendCapture(request, `to delete ${stamp}`)
  await page.goto('/')
  await page.getByRole('button', { name: 'Inbox' }).click()
  const card = page.getByRole('listitem').filter({ hasText: `Capture #${id}` })
  await card.getByRole('button', { name: 'Delete' }).click()
  await expect(card).toHaveCount(0)
  expect((await request.get(`/api/captures/${id}`)).status()).toBe(404)
})
