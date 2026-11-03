import { expect, openItem, section, test } from './lib'

// My inventory: the list, an item's facts and photos, its values with where each came from,
// what you know added by hand, and the history. After the build shots: a change to an item
// changes the inventory the recorded proposals were made from. Accepting and rejecting a value
// is shot on a label read just now (12-capture.spec.ts).

const MONITOR = 'Dell U2419H monitor, 24 inch'

test.describe.configure({ mode: 'serial' })

test('the list', async ({ shots, page }) => {
  await page.goto('/#inventory')
  await expect(page.getByRole('table', { name: 'Items' })).toBeVisible()
  await shots.take('01-list')
})

test('an item, its photos and its values with their sources', async ({ shots, page }) => {
  const item = await openItem(page, MONITOR)
  await shots.take('02-item')
  await shots.show(item.getByRole('table', { name: 'Fields' }))
  await shots.take('03-values')
})

test('what you know, added by hand', async ({ shots, page }) => {
  const item = await openItem(page, MONITOR)
  await item.getByLabel('Field', { exact: true }).fill('Stand')
  await item.getByLabel('Value', { exact: true }).fill('height-adjustable, included')
  await shots.show(item.getByRole('button', { name: 'Add field' }), 'center')
  await shots.take('06-add-what-you-know')
  await item.getByRole('button', { name: 'Add field' }).click()
  await expect(item.getByRole('table', { name: 'Fields' })).toContainText('height-adjustable')
  await item.getByRole('button', { name: 'History' }).click()
  const history = item.getByRole('list', { name: 'History' })
  await expect(history).toBeVisible()
  await shots.show(history, 'center')
  await shots.take('07-history')
})

test('the sections of an item', async ({ shots, page }) => {
  const item = await openItem(page, MONITOR)
  await section(item, 'Picture')
  await shots.take('08-picture-section')
})
