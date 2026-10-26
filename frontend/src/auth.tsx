import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export interface User { id: number; email: string; name: string }
interface AuthState { user: User | null; ready: boolean; signIn: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>; signOut: () => Promise<void> }

const Ctx = createContext<AuthState | null>(null)

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/auth/${path}`, { method: 'POST', credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) {
    const b = await res.json().catch(() => null)
    throw new Error(typeof b?.detail === 'string' ? b.detail : 'Something went wrong. Try again.')
  }
  return res.json()
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'same-origin' }).then(r => (r.ok ? r.json() : null)).then(u => setUser(u ?? null)).catch(() => setUser(null)).finally(() => setReady(true))
  }, [])
  const signIn = useCallback(async (email: string, password: string) => setUser(await post<User>('login', { email, password })), [])
  const register = useCallback(async (name: string, email: string, password: string) => setUser(await post<User>('register', { name, email, password })), [])
  const signOut = useCallback(async () => { await post('logout').catch(() => null); setUser(null) }, [])
  return <Ctx.Provider value={{ user, ready, signIn, register, signOut }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used inside AuthProvider')
  return c
}
