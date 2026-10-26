import { expect, test } from '@playwright/test'
import { removeTestUser, TEST_EMAIL } from './helpers'

test.afterAll(() => removeTestUser())

test('sign-in page: clear errors, create account, sign out', async ({ page }) => {
  removeTestUser()
  await page.goto('/signin')
  await page.fill('#si-email', 'someone@gmail.com'); await page.fill('#si-pw', 'whatever-123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('incorrect')
  await page.getByRole('button', { name: 'Create an account' }).click()
  await page.fill('#si-name', 'E2E Tester'); await page.fill('#si-email', 'someone@gmail.com'); await page.fill('#si-pw', 'short')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('alert')).toContainText(/yale\.edu|10 characters/)
  await page.fill('#si-email', TEST_EMAIL); await page.fill('#si-pw', `pw-${Date.now()}-${Math.random()}`)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('.nav-user__name')).toHaveText('E2E')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.locator('.nav-signin')).toBeVisible()
})
