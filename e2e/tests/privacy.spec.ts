import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { grayPng } from './png'

// A made-up label (every value on it is fake); the backend's one recorded photo check is of
// this very file, so the areas it found answer in fixture mode.
const sticker = readFileSync(new URL('./fake-sticker.png', import.meta.url))
const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  return page.getByRole('article', { name: `Item ${name}` })
}

test('a photo with private details says what is hidden, and the owner can show an area', async ({ page, request }) => {
  const name = `Router sticker ${stamp}`
  const created = await request.post('/api/items', { data: { item_type: 'router', name } })
  expect(created.status()).toBe(201)
  const id = ((await created.json()) as { id: number }).id
  const sent = await request.post(`/api/items/${id}/photos`, {
    multipart: { uploads: { name: 'sticker.png', mimeType: 'image/png', buffer: sticker } },
  })
  expect(sent.status()).toBe(201)

  const panel = await openItem(page, name)
  const notes = panel.getByRole('list', { name: 'Private details' })
  await expect(notes).toHaveText('6 areas hidden: product key, MAC address, password or PIN, serial number, barcode, QR code.')
  // opened, the original shows the areas outlined, and each can be shown on shared copies
  await panel.getByRole('button', { name: 'Item photo 1', exact: true }).click()
  await expect(panel.locator('.privacy-box')).toHaveCount(6)
  const areas = panel.getByLabel('Areas on photo 1')
  await areas.getByRole('button', { name: 'Show barcode' }).click()
  await expect(notes).toHaveText('5 areas hidden: product key, MAC address, password or PIN, serial number, QR code; 1 shown by the owner: barcode.')
  await expect(areas.getByRole('button', { name: 'Hide barcode' })).toBeVisible()
})

test('a photo nothing could check is kept out of anything shared, and says so', async ({ page, request }) => {
  const name = `Unchecked photo ${stamp}`
  const created = await request.post('/api/items', { data: { item_type: 'adapter', name } })
  const id = ((await created.json()) as { id: number }).id
  // a photo no recording answers: the check cannot finish in fixture mode
  const sent = await request.post(`/api/items/${id}/photos`, {
    multipart: { uploads: { name: 'gray.png', mimeType: 'image/png', buffer: grayPng(320, 240) } },
  })
  expect(sent.status()).toBe(201)
  const panel = await openItem(page, name)
  await expect(panel.getByRole('list', { name: 'Private details' })).toContainText('kept out of anything shared')
  await expect(panel.getByRole('button', { name: 'Check for private details' })).toBeVisible()
})
