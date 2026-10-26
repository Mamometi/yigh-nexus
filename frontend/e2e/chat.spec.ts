import { expect, test } from '@playwright/test'

test('assistant: starters, answers with working links, new chat clears', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Ask the YIGH assistant' }).click()
  await page.locator('.chat__starters button', { hasText: 'Who works on malaria' }).click()
  const reply = page.locator('.chat__msg--assistant').last()
  await expect(reply).toContainText('Faculty matching', { timeout: 30000 })
  const link = reply.locator('a[href^="/faculty/"]').first()
  const name = (await link.innerText()).trim()
  await link.click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText(name.split(',')[0])
  await expect(page.locator('.chat__msg')).toHaveCount(2)
  await page.locator('.chat__form textarea').fill('when is NIH opening again')
  await page.keyboard.press('Enter')
  await expect(page.locator('.chat__msg--assistant').last()).toContainText('National Institutes of Health', { timeout: 30000 })
  await page.getByRole('button', { name: 'New chat' }).click()
  await expect(page.locator('.chat__msg')).toHaveCount(0)
})
