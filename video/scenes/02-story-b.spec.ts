import { expect, openItem, test, type Scene } from './lib'
import type { Locator } from '@playwright/test'

// Story B, unused electronics: the inventory, the skills profile and what the owner wants from
// a build, the proposals, one selected with its items committed, drawn, what it still needs
// as a Marketplace search, and the build pack. One project carries the shots after
// the proposals: the arcade when the proposals have one, else the first proposed. Then what is
// not built with: the graphics card's price guidance, a voice note becoming its condition
// notes, and its draft in Marketplace's fields.

test.describe.configure({ mode: 'serial' })

const GPU = 'EVGA GeForce 9800 GT graphics card'
// a short spoken note in WAV, the condition the demo set states for the card
const NOTE = 'notes/gpu-note.wav'

const INTERESTS = 'a tabletop arcade for the living room; home automation; a smart mirror in the hall'

async function project(scene: Scene): Promise<Locator> {
  const { page } = scene
  await scene.click(page.getByRole('button', { name: 'Build and reuse', exact: true }))
  const table = page.getByRole('table', { name: 'Projects' })
  const arcade = table.getByRole('row', { name: /arcade/i })
  const row = (await arcade.count()) > 0 ? arcade.first() : table.getByRole('row').filter({ hasText: 'proposed' }).or(table.getByRole('row').filter({ hasText: 'selected' })).first()
  await scene.click(row.getByRole('button', { name: 'Open' }))
  return page.getByRole('article', { name: /^Project / })
}

test('S10 the inventory', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#inventory')
  await expect(page.getByRole('table', { name: 'Items' })).toBeVisible()
  await scene.ready()
  await scene.point(page.getByRole('table', { name: 'Items' }).getByRole('row').nth(1))
  await scene.scroll(420, 2200)
  await scene.hold(600)
  await scene.scroll(-420, 1200)
  await scene.hold(800)
})

test('S11 the skills profile and what I want from a build', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#profile')
  const form = page.getByRole('form', { name: 'Profile' })
  await expect(form).toBeVisible()
  await scene.ready()
  await scene.click(form.getByLabel('software: confident'), 300)
  await scene.click(form.getByLabel('electronics and soldering: some'), 300)
  await scene.click(form.getByRole('button', { name: 'Save profile' }), 600)
  await scene.click(page.getByRole('button', { name: 'Build and reuse', exact: true }))
  const prefs = page.getByRole('form', { name: 'What I want from a build' })
  await scene.click(prefs.getByRole('button', { name: 'Edit' }))
  await scene.type(prefs.getByLabel('Interests'), INTERESTS, 12)
  await scene.type(prefs.getByLabel('Budget'), '120')
  await scene.click(prefs.getByRole('button', { name: 'Save' }))
  await expect(prefs).toContainText('saved')
  await scene.hold(900)
})

test('S12 five proposals from what I own', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#build')
  const form = page.getByRole('form', { name: 'Propose projects' })
  await expect(form).toBeVisible()
  await scene.ready()
  await scene.reveal(form, 'start')
  await scene.click(form.getByLabel('How many'), 200)
  await form.getByLabel('How many').selectOption('5')
  await scene.click(form.getByRole('button', { name: 'Propose' }))
  // without a recording of this request the stub may keep nothing: the demo set's own
  // proposals stay in the table, and the generator marks the shot as a stand-in
  await expect(form).toContainText(/proposed|No idea fits/, { timeout: 150_000 })
  scene.mark('proposed')
  await scene.settle(300)
  // a proposal may open on its own; the table is the shot
  const close = page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true })
  if (await close.count()) await scene.click(close.first(), 300)
  const table = page.getByRole('table', { name: 'Projects' })
  await scene.reveal(table)
  await scene.point(table.getByRole('row').nth(1))
  await scene.hold(800)
  const arcade = table.getByRole('row', { name: /arcade/i })
  if (await arcade.count()) await scene.point(arcade.first())
  await scene.hold(1800)
})

test('S13 the build selected, its items committed', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#build')
  await scene.ready()
  const panel = await project(scene)
  await scene.point(panel.getByRole('list', { name: 'Items on this project' }))
  await scene.hold(900)
  const missing = panel.getByRole('list', { name: 'Missing requirements' })
  if (await missing.count()) {
    await scene.point(missing)
    await scene.hold(700)
  }
  await scene.click(panel.getByRole('button', { name: 'Select and commit the items' }))
  const move = panel.getByRole('button', { name: 'Move it here' })
  await expect(panel.getByText('selected: items committed').or(move)).toBeVisible()
  if (await move.isVisible()) await scene.click(move)
  await expect(panel).toContainText('selected: items committed')
  await scene.point(panel.getByRole('list', { name: 'Items on this project' }))
  await scene.hold(1600)
})

test('S14 Draw it: how the finished build could look', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#build')
  await scene.ready()
  const panel = await project(scene)
  const draw = panel.getByRole('button', { name: /^Draw it: / })
  await scene.click(draw)
  const picture = panel.getByRole('img', { name: /^Illustrative picture/ })
  await expect(picture).toBeVisible({ timeout: 120_000 })
  scene.mark('drawn')
  await scene.settle(500)
  await scene.point(picture)
  await scene.hold(2500)
})

test('S15 what is missing, as a Marketplace search', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#build')
  await scene.ready()
  const panel = await project(scene)
  const missing = panel.getByRole('list', { name: 'Missing requirements' })
  const need = missing.getByRole('listitem').first()
  // the requirement's own words, up to its first bracket, name the search it starts
  const words = ((await need.textContent()) ?? '').split(/[(·]/)[0].trim()
  await scene.click(need.getByRole('button', { name: 'Find it on Marketplace' }))
  await expect(need).toContainText('open on Find a part')
  await scene.hold(700)
  await scene.click(page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }), 300)
  await scene.click(page.getByRole('button', { name: 'Find a part', exact: true }))
  const row = page.getByRole('table', { name: 'Searches' }).getByRole('row').filter({ hasText: words.slice(0, 30) }).first()
  await scene.click(row.getByRole('button', { name: 'Open' }))
  const search = page.getByRole('article', { name: /^Search / })
  const link = search.getByRole('link', { name: 'Search Marketplace' })
  // pointed at, never opened: no Marketplace page on camera
  await scene.point(link)
  await scene.hold(2200)
})

test('S16 the build pack', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#build')
  await scene.ready()
  const panel = await project(scene)
  const packs = panel.getByRole('region', { name: 'Build pack' })
  await scene.reveal(packs)
  await scene.click(packs.getByRole('button', { name: 'Write the build pack' }))
  await expect(packs.getByRole('list', { name: 'Packs' })).toContainText('version 1')
  await scene.point(packs.getByRole('link', { name: 'Download' }).first())
  await scene.hold(2200)
})

test('S17 the graphics card: what it is worth', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#inventory')
  await scene.ready()
  const item = await openItem(scene, GPU)
  await scene.click(item.getByRole('navigation', { name: 'Sections' }).getByRole('button', { name: 'Value', exact: true }), 1000)
  const value = item.getByRole('region', { name: 'What is it worth?' })
  const guide = value.getByRole('status').first()
  await expect(guide).toBeVisible()
  // the figures kept apart, then the pages they come from
  await scene.reveal(guide, 'start')
  await scene.point(guide.getByRole('table', { name: 'Quantities' }))
  await scene.hold(1600)
  const comparables = guide.getByRole('list', { name: 'Comparables' })
  if (await comparables.count()) {
    await scene.reveal(comparables, 'center')
    await scene.point(comparables.getByRole('listitem').first())
  }
  await scene.hold(1800)
})

test('S18 a voice note, then the draft in Marketplace fields', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#inventory')
  await scene.ready()
  const item = await openItem(scene, GPU)
  await scene.click(item.getByRole('navigation', { name: 'Sections' }).getByRole('button', { name: 'Sell or give away', exact: true }), 1000)
  const details = item.getByRole('form', { name: 'Listing details' })
  const voice = details.getByLabel('Voice note (WAV)')
  await scene.point(voice)
  await scene.hold(300)
  await voice.setInputFiles(NOTE)
  const heard = details.getByText(/Transcribed and saved as condition notes/)
  await expect(heard).toBeVisible({ timeout: 90_000 })
  scene.mark('heard')
  await scene.settle(300)
  await scene.point(heard)
  await scene.hold(1600)
  await scene.click(details.getByRole('button', { name: 'Write the draft' }))
  const handoff = item.getByRole('region', { name: 'Marketplace handoff' })
  await expect(handoff.getByRole('status').first()).toContainText('draft 2', { timeout: 120_000 })
  scene.mark('drafted')
  await scene.settle(300)
  const fields = handoff.getByLabel('Fields to paste')
  await scene.reveal(fields, 'start')
  await scene.point(fields.getByRole('button', { name: 'Copy title' }))
  await scene.hold(1000)
  // pointed at, never opened: no Marketplace page on camera
  await scene.point(handoff.getByRole('button', { name: 'Download photos' }))
  await scene.hold(700)
  await scene.point(handoff.getByRole('link', { name: 'Open Marketplace' }))
  await scene.hold(1600)
})
