import { useEffect, useState } from 'react'

/** "My project": things people save while browsing (funding calls, faculty, partner organizations).
 *  Kept in this browser (localStorage), so it works without signing in and survives server restarts. */

export type SavedKind = 'funding' | 'faculty' | 'partner' | 'guide'
export interface SavedItem { kind: SavedKind; id: number | string; title: string; sub?: string | null; url?: string | null }

const KEY = 'grapph-project'
const read = (): SavedItem[] => { try { return JSON.parse(localStorage.getItem(KEY) ?? '[]') } catch { return [] } }

export function useProject() {
  const [items, setItems] = useState<SavedItem[]>(read)
  useEffect(() => {
    const sync = () => setItems(read())
    window.addEventListener('grapph-project', sync)
    window.addEventListener('storage', sync)
    return () => { window.removeEventListener('grapph-project', sync); window.removeEventListener('storage', sync) }
  }, [])
  const write = (next: SavedItem[]) => { localStorage.setItem(KEY, JSON.stringify(next)); window.dispatchEvent(new Event('grapph-project')) }
  const has = (kind: SavedKind, id: number | string) => items.some(i => i.kind === kind && i.id === id)
  const toggle = (it: SavedItem) => write(has(it.kind, it.id) ? items.filter(i => !(i.kind === it.kind && i.id === it.id)) : [...items, it])
  const remove = (kind: SavedKind, id: number | string) => write(items.filter(i => !(i.kind === kind && i.id === id)))
  return { items, has, toggle, remove }
}
