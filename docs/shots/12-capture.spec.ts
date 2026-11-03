import { expect, PHOTOS, test } from './lib'

// Read a label from the computer (regions found first, then the values with where each came
// from, saved privately, then accepted or rejected one by one in the inventory), and the
// Inbox: a capture sent from this computer. Read it is not shot: a capture's photos are
// re-encoded on arrival, so no recording matches its request, and the answer would be a
// stand-in made for another item.

test.describe.configure({ mode: 'serial' })

test('Read a label: regions, values with their sources, saved', async ({ shots, page }) => {
  await page.goto('/')
  await expect(page.getByLabel('Photos of the label')).toBeVisible()
  await shots.take('01-read-a-label')
  await page.getByLabel('Photos of the label').setInputFiles(`${PHOTOS}/dell-u2419h-label.jpg`)
  await shots.take('02-photo-chosen')
  await page.getByRole('button', { name: 'Read the label' }).click()
  const table = page.getByRole('table', { name: 'Evidence' })
  await expect(table).toBeVisible({ timeout: 120_000 })
  const segments = page.locator('section.segments')
  if (await segments.count()) {
    await shots.show(segments.first())
    await shots.take('03-regions')
  }
  await shots.show(table)
  await shots.take('04-values')
  await page.getByLabel('Name').fill('Spare Dell monitor from the office')
  await shots.show(page.getByRole('button', { name: 'Save privately' }), 'center')
  await shots.take('05-save')
  await page.getByRole('button', { name: 'Save privately' }).click()
  await expect(page.getByRole('heading', { name: 'My inventory' })).toBeVisible()

  // the values just read wait to be confirmed: the inventory guide's steps
  shots.guide = 'inventory'
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name: /Spare Dell monitor from the office/ }).getByRole('button', { name: 'Open' }).click()
  const item = page.getByRole('article', { name: /^Item Spare Dell monitor from the office/ })
  const fields = item.getByRole('table', { name: 'Fields' })
  await expect(fields.getByRole('button', { name: 'Accept' }).first()).toBeVisible()
  await shots.show(fields)
  await shots.take('04-to-confirm')
  const rows = fields.getByRole('row').filter({ has: page.getByRole('button', { name: 'Accept' }) })
  const waiting = await rows.count()
  await rows.first().getByRole('button', { name: 'Accept' }).click()
  await expect(rows).toHaveCount(waiting - 1)
  // a rejected value leaves the current values (it stays in the record)
  const last = (await rows.last().getByRole('rowheader').textContent()) ?? ''
  await rows.last().getByRole('button', { name: 'Reject' }).click()
  await expect(fields.getByRole('rowheader', { name: last, exact: true })).toHaveCount(0)
  await shots.show(fields)
  await shots.take('05-accepted-rejected')
})

test('Inbox: a capture sent from this computer', async ({ shots, page }) => {
  await page.goto('/#inbox')
  const form = page.getByRole('form', { name: 'Send a capture' })
  await expect(form).toBeVisible()
  await shots.take('06-inbox')
  await form.getByText('Send a capture from this computer').click()
  await form.getByLabel('Photos').setInputFiles([`${PHOTOS}/tplink-pa2010.jpg`, `${PHOTOS}/tplink-pa2010-label.jpg`])
  await form.getByLabel('Name (optional)').fill('Powerline adapter from the hall closet')
  await form.getByLabel('What you know (optional)').fill('one unit, still in its wrap')
  await shots.show(form)
  await shots.take('07-send-a-capture')
  await form.getByRole('button', { name: 'Send' }).click()
  await expect(form).toContainText(/Sent as capture #\d+/)
  const card = page.getByRole('listitem').filter({ hasText: 'Powerline adapter from the hall closet' })
  await expect(card).toBeVisible()
  await shots.show(card, 'center')
  await shots.take('08-capture-received')
})
