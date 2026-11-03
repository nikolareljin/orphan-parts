import { expect, test } from './lib'
import type { Locator, Page } from '@playwright/test'

// Build and reuse: proposals from what you own, one selected with its items committed, drawn,
// what it still needs as a Marketplace search, and the build pack. One project carries the
// shots: the arcade when the proposals have one, else the first proposed.

test.describe.configure({ mode: 'serial' })

async function project(page: Page): Promise<Locator> {
  await page.goto('/#build')
  const table = page.getByRole('table', { name: 'Projects' })
  const arcade = table.getByRole('row', { name: /arcade/i })
  const row = (await arcade.count()) > 0 ? arcade.first() : table.getByRole('row').filter({ hasText: /proposed|selected/ }).first()
  await row.getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: /^Project / })
  await expect(panel).toBeVisible()
  return panel
}

test('proposals from what I own', async ({ shots, page }) => {
  await page.goto('/#build')
  const form = page.getByRole('form', { name: 'Propose projects' })
  await expect(form).toBeVisible()
  await form.getByLabel('How many').selectOption('5')
  await shots.show(form)
  await shots.take('01-propose')
  await form.getByRole('button', { name: 'Propose' }).click()
  await expect(form).toContainText(/proposed|No idea fits/, { timeout: 150_000 })
  const close = page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true })
  if (await close.count()) await close.first().click()
  const table = page.getByRole('table', { name: 'Projects' })
  await shots.show(table, 'center')
  await shots.take('02-proposals')
})

test('a project: its items, what it still needs, what to check', async ({ shots, page }) => {
  const panel = await project(page)
  await shots.take('03-project')
})

test('select it and commit the items', async ({ shots, page }) => {
  const panel = await project(page)
  // the demo set selects its projects; on a set that does not, select it here
  const select = panel.getByRole('button', { name: 'Select and commit the items' })
  if (await select.count()) await select.click()
  const move = panel.getByRole('button', { name: 'Move it here' })
  await expect(panel.getByText('selected: items committed').or(move)).toBeVisible()
  if (await move.isVisible()) await move.click()
  await expect(panel).toContainText('selected: items committed')
  await shots.show(panel.getByRole('list', { name: 'Items on this project' }), 'center')
  await shots.take('04-selected')
})

test('Draw it', async ({ shots, page }) => {
  const panel = await project(page)
  await panel.getByRole('button', { name: /^Draw (it|again): / }).click()
  // the demo set draws each project once: the new picture joins the one kept
  const picture = panel.getByRole('img', { name: /^Illustrative picture/ }).last()
  await expect(picture).toBeVisible({ timeout: 120_000 })
  await expect.poll(() => picture.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await shots.show(picture, 'center')
  await shots.take('05-drawn')
})

test('what is missing, as a Marketplace search', async ({ shots, page }) => {
  const panel = await project(page)
  const need = panel.getByRole('list', { name: 'Missing requirements' }).getByRole('listitem').first()
  const words = ((await need.textContent()) ?? '').split(/[(·]/)[0].trim()
  await need.getByRole('button', { name: 'Find it on Marketplace' }).click()
  await expect(need).toContainText('open on Find a part')
  await shots.show(need, 'center')
  await shots.take('06-find-it')
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Find a part', exact: true }).click()
  const row = page.getByRole('table', { name: 'Searches' }).getByRole('row').filter({ hasText: words.slice(0, 30) }).first()
  await row.getByRole('button', { name: 'Open' }).click()
  const search = page.getByRole('article', { name: /^Search / })
  await shots.show(search.getByRole('link', { name: 'Search Marketplace' }), 'center')
  await shots.take('07-search-from-build')
})

test('the build pack', async ({ shots, page }) => {
  const panel = await project(page)
  const packs = panel.getByRole('region', { name: 'Build pack' })
  await packs.getByRole('button', { name: /^(Write the build pack|Write it again)$/ }).click()
  await expect(packs.getByRole('list', { name: 'Packs' })).toContainText('version 1')
  await expect(packs.getByLabel(/^Build pack \d/)).toBeVisible()
  await shots.show(packs, 'center')
  await shots.take('08-build-pack')
})
