import { expect, test } from './lib'

// Profile: the skills and their levels, a skill of your own, the tools; then what you want
// from a build on Build and reuse. The levels and the build wishes are the demo video's, so the
// proposals after them replay its recording.

const INTERESTS = 'a tabletop arcade for the living room; home automation; a smart mirror in the hall'

test.describe.configure({ mode: 'serial' })

test('skills and levels', async ({ shots, page }) => {
  await page.goto('/#profile')
  const form = page.getByRole('form', { name: 'Profile' })
  await expect(form).toBeVisible()
  await shots.take('01-skills')
  await form.getByLabel('software: confident').check()
  await form.getByLabel('electronics and soldering: some').check()
  await shots.take('02-levels-set')
  await form.getByRole('button', { name: 'Save profile' }).click()
  await expect(form).toContainText('saved')
})

test('a skill of your own and the tools you have, shown, not saved', async ({ shots, page }) => {
  await page.goto('/#profile')
  const form = page.getByRole('form', { name: 'Profile' })
  await form.getByLabel('Another skill').fill('bike repair')
  await form.getByLabel('Level').selectOption('some')
  await form.getByLabel('Tools I have').fill('soldering iron, multimeter, drill')
  await shots.show(form.getByLabel('Another skill'), 'center')
  await shots.take('03-own-skill-and-tools')
})

test('what I want from a build', async ({ shots, page }) => {
  await page.goto('/#build')
  const prefs = page.getByRole('form', { name: 'What I want from a build' })
  await prefs.getByRole('button', { name: 'Edit' }).click()
  await prefs.getByLabel('Interests').fill(INTERESTS)
  await prefs.getByLabel('Budget').fill('120')
  await shots.take('04-build-wishes')
  await prefs.getByRole('button', { name: 'Save' }).click()
  await expect(prefs).toContainText('saved')
  await shots.take('05-build-wishes-saved')
})
