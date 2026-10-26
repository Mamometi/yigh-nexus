import type { APIRequestContext } from '@playwright/test'

export const PRIORITIES = ['Climate & Health', 'Digital Health & AI', 'Health Diplomacy & Security', 'Health Sovereignty']

export async function api<T = any>(request: APIRequestContext, path: string): Promise<T> {
  const res = await request.get(`/api${path}`)
  if (!res.ok()) throw new Error(`${path} -> ${res.status()}`)
  return res.json()
}

const detailCache = new Map<number, any>()
export async function detail(request: APIRequestContext, id: number) {
  if (!detailCache.has(id)) detailCache.set(id, await api(request, `/faculty/${id}`))
  return detailCache.get(id)
}

/** Every searchable text field of a profile, lowercased. */
export function sourceText(d: any): Record<string, string> {
  const s = d.source
  return {
    title: (d.title ?? '').toLowerCase(),
    bio: (s.bio ?? '').toLowerCase(),
    research_interests: s.research_interests.join('; ').toLowerCase(),
    activities: s.activities.map((a: any) => `${a.title ?? ''}. ${a.synopsis ?? ''}`).join(' ').toLowerCase(),
    activity_locations: s.activities.flatMap((a: any) => a.locations).join('; ').toLowerCase(),
    organizations: s.organizations.map((o: any) => o.name).join('; ').toLowerCase(),
  }
}

export const norm = (s: string) => s.toLowerCase().replace(/\s+/g, ' ').replace(/^…|…$/g, '').trim()

import { execFileSync } from 'node:child_process'
import path from 'node:path'
import type { Page } from '@playwright/test'

export const TEST_EMAIL = 'e2e.clickthrough@yale.edu'
const AUTH_DB = path.resolve(process.cwd(), '../data/auth.db')

/** Throwaway local account for signed-in checks; password is random and never stored anywhere. */
export async function signIn(page: Page) {
  const password = `e2e-${Math.random().toString(36).slice(2)}-${Date.now()}`
  removeTestUser()
  const r = await page.request.post('/api/auth/register', { data: { email: TEST_EMAIL, name: 'E2E Tester', password } })
  if (!r.ok()) throw new Error(`register failed ${r.status()}`)
}

export function removeTestUser() {
  execFileSync('sqlite3', [AUTH_DB, `delete from sessions where user_id in (select id from users where email='${TEST_EMAIL}'); delete from users where email='${TEST_EMAIL}';`])
}

/** Collect console errors (ignoring expected 401s from signed-out checks). */
export function watchErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error' && !/401|Unauthorized/.test(m.text())) errors.push(m.text()) })
  return errors
}
