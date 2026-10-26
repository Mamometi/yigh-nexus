import { useMemo, useState } from 'react'
import { watch, type WatchSource } from '../api'
import { fmtDate } from './OppCardView'
import { ErrorState, Loading } from './StateViews'
import { useAsync } from '../hooks'

export const METHODS: Record<WatchSource['access_method'], { label: string; help: string }> = {
  api: { label: 'Official API', help: 'Structured records read from the funder’s own API; details verified field by field.' },
  rss: { label: 'Official feed', help: 'The funder’s RSS feed, cross-checked against official records.' },
  html_listing: { label: 'Listing collector', help: 'Each call is read from the funder’s own listing or call page; values only when labelled.' },
  page_monitor: { label: 'Change monitor', help: 'The page is checked weekly; any change is queued for a person to review. No details are extracted.' },
  manual: { label: 'Manual', help: 'Not read automatically (access blocked, invitation-only, or no readable page). Check the link yourself.' },
}
const ORDER: WatchSource['access_method'][] = ['api', 'rss', 'html_listing', 'page_monitor', 'manual']

export function Watchlist() {
  const [state, retry] = useAsync(watch.sources, [])
  const [q, setQ] = useState('')
  const groups = useMemo(() => {
    if (state.status !== 'success') return []
    const rows = state.data.filter(s => !q || (s.name + ' ' + (s.notes ?? '')).toLowerCase().includes(q.toLowerCase()))
    return ORDER.map(m => [m, rows.filter(s => s.access_method === m)] as const).filter(([, r]) => r.length)
  }, [state, q])
  if (state.status === 'loading') return <Loading label="Loading the watchlist…" />
  if (state.status === 'error') return <ErrorState message={state.error} onRetry={retry} />
  const all = state.data
  return (
    <section aria-label="Funder watchlist">
      <div className="card watch__changes"><PageChanges /></div>
      <div className="watch__summary">
        <p><strong>{all.length}</strong> funder sources · <strong>{all.filter(s => s.enabled).length}</strong> checked automatically every Monday ·{' '}
          <strong>{all.filter(s => s.page_change_pending).length}</strong> page changes awaiting review</p>
        <input className="input watch__search" placeholder="Filter funders…" value={q} onChange={e => setQ(e.target.value)} aria-label="Filter funders" />
      </div>
      {groups.map(([m, rows]) => (
        <div key={m} className="watch__group">
          <h3>{METHODS[m].label} <span className="muted small">({rows.length})</span></h3>
          <p className="muted small">{METHODS[m].help}</p>
          <table className="table watch__table">
            <thead><tr><th>Funder / source</th><th>Last checked</th><th>Status</th><th>Opportunities</th><th>Notes</th></tr></thead>
            <tbody>
              {rows.map(s => (
                <tr key={s.id}>
                  <td><a href={s.official_url} target="_blank" rel="noreferrer">{s.name}</a>
                    {s.page_change_pending && <span className="badge badge--change">page changed</span>}</td>
                  <td className="small">{s.enabled ? fmtDate(s.last_checked_at?.slice(0, 10)) ?? 'not yet' : '—'}</td>
                  <td><span className={`src-status src-status--${s.enabled ? s.last_status ?? 'pending' : 'manual'}`}>
                    {s.enabled ? s.last_status ?? 'pending' : 'manual'}</span>{s.last_error && <div className="small muted">{s.last_error}</div>}</td>
                  <td className="small">{s.opportunities.total ? `${s.opportunities.open} open / ${s.opportunities.total}` : '—'}</td>
                  <td className="small watch__notes">{s.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  )
}

export function PageChanges() {
  const [state, retry] = useAsync(watch.review, [])
  const [done, setDone] = useState<number[]>([])
  if (state.status === 'loading') return null
  if (state.status === 'error') return <ErrorState message={state.error} onRetry={retry} />
  const pages = state.data.changed_pages.filter(p => !done.includes(p.id))
  return (
    <div>
      <h3>Monitored pages that changed</h3>
      {pages.length === 0 ? <p className="muted small">No unreviewed changes. Funders on change monitors (Ford, Wellcome, Packard, Rockefeller and others) are re-checked every Monday.</p> : (
        <ul className="brief__list">
          {pages.map(p => (
            <li key={p.id}>
              <a href={p.url} target="_blank" rel="noreferrer">{p.source}</a> <span className="muted small">· changed {fmtDate(p.retrieved_at.slice(0, 10))}</span>
              {p.excerpt && <p className="small muted">{p.excerpt.slice(0, 220)}…</p>}
              <button className="link-btn small" onClick={() => watch.markReviewed(p.id).then(() => setDone(d => [...d, p.id]))}>Mark reviewed</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
