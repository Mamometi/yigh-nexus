import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type FacultyCard } from '../api'
import { Photo } from '../components/Photo'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { Chip, PRIORITY_COLORS, PriorityChip } from '../components/Tags'
import { useAsync, useDebounced } from '../hooks'

const PRIORITIES = [['climate-health', 'Climate & Health'], ['digital-health-ai', 'Digital Health & AI'],
                    ['health-diplomacy-security', 'Health Diplomacy & Security'], ['health-sovereignty', 'Health Sovereignty']]

export function FacultyDirectory() {
  const [params, setParams] = useSearchParams()
  const [text, setText] = useState(params.get('q') ?? '')
  const q = useDebounced(text.trim(), 300)
  const get = (k: string) => params.get(k) ?? undefined
  const set = (k: string, v?: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }) }
  const [filters] = useAsync(api.filters, [])
  const [list, retry] = useAsync(() => api.faculty({ q: q || undefined, priority: get('priority'), school: get('school'), keyword: get('keyword'),
                                                     region: get('region'), directory: get('directory') }), [q, get('priority'), get('school'), get('keyword'), get('region'), get('directory')])
  const clear = () => { setText(''); setParams(new URLSearchParams(), { replace: true }) }

  return (
    <div className="page fdir osf">
      <header className="osf-head fdir-head">
        <div className="osf-head__inner">
        <p className="eyebrow eyebrow--light">Faculty Directory</p>
        <h1>Yale faculty working in global health</h1>
        <p className="lede">Meet the YIGH-affiliated and Yale School of Public Health faculty whose work involves global health:
          what they study, where they work, and how it connects to YIGH’s strategic priorities.</p>
        </div>
        <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>
      </header>

      {filters.status === 'success' && (
        <nav className="fdir-tabs" aria-label="Yale school">
          <button className={!get('school') ? 'is-on' : ''} aria-pressed={!get('school')} onClick={() => set('school')}>All schools <span>{filters.data.total_faculty}</span></button>
          {filters.data.schools.map(sc => (
            <button key={sc.value} className={get('school') === sc.value ? 'is-on' : ''} aria-pressed={get('school') === sc.value}
                    onClick={() => set('school', get('school') === sc.value ? undefined : sc.value)}>{sc.label} <span>{sc.count}</span></button>
          ))}
        </nav>
      )}

      <section className="fbar card" aria-label="Filters">
        <div className="fbar__row">
          <div className="field fbar__search"><label htmlFor="fd-q">Search</label>
            <input id="fd-q" type="search" className="input" value={text} placeholder="Name, topic or place"
                   onChange={e => { setText(e.target.value); set('q', e.target.value || undefined) }} /></div>
          {filters.status === 'success' && (<>
            <div className="field"><label htmlFor="fd-kw">Research area</label>
              <select id="fd-kw" value={get('keyword') ?? ''} onChange={e => set('keyword', e.target.value || undefined)}>
                <option value="">All research areas</option>{filters.data.keywords.map(k => <option key={k.value} value={k.value}>{k.label} ({k.count})</option>)}</select></div>
            <div className="field"><label htmlFor="fd-geo">Geographic focus</label>
              <select id="fd-geo" value={get('region') ?? ''} onChange={e => set('region', e.target.value || undefined)}>
                <option value="">Anywhere</option>
                <optgroup label="Regions">{filters.data.regions.filter(r => r.kind === 'region').map(r => <option key={r.value} value={r.value}>{r.label} ({r.count})</option>)}</optgroup>
                <optgroup label="Countries">{filters.data.regions.filter(r => r.kind !== 'region').map(r => <option key={r.value} value={r.value}>{r.label} ({r.count})</option>)}</optgroup>
              </select></div>
            <div className="field"><label htmlFor="fd-dir">Directory</label>
              <select id="fd-dir" value={get('directory') ?? ''} onChange={e => set('directory', e.target.value || undefined)}>
                <option value="">All faculty</option>{filters.data.directories.map(d => <option key={d.value} value={d.value}>{d.label} ({d.count})</option>)}</select></div>
          </>)}
        </div>
        <div className="fbar__row fbar__row--prios" role="group" aria-label="YIGH strategic priority">
          <span className="fdir__label">YIGH priority</span>
            <div className="priority-list priority-list--row">
              {PRIORITIES.map(([slug, label]) => {
                const count = filters.status === 'success' ? filters.data.priorities.find(p => p.value === slug)?.count : undefined
                return (
                  <button key={slug} className={`priority-opt ${get('priority') === slug ? 'is-on' : ''}`} aria-pressed={get('priority') === slug}
                          style={{ '--c': PRIORITY_COLORS[slug] } as React.CSSProperties} onClick={() => set('priority', get('priority') === slug ? undefined : slug)}>
                    <span className="dot" /><span className="priority-opt__label">{label}</span>{count !== undefined && <span className="count">{count}</span>}
                  </button>
                )
              })}
            </div>
          {params.toString() && <button className="link-btn fbar__clear" onClick={clear}>Clear all</button>}
        </div>
      </section>

      <section aria-live="polite">
          <div className="results__bar"><p>{list.status === 'success' && <><strong>{list.data.length}</strong> faculty</>}</p>
            <p className="muted small">Priorities and research areas are picked out automatically from each Yale profile. Open a profile to see why.</p></div>
          {list.status === 'loading' && <Loading label="Loading faculty…" />}
          {list.status === 'error' && <ErrorState message={list.error} onRetry={retry} />}
          {list.status === 'success' && list.data.length === 0 && (
            <EmptyState title="No faculty match" action={<button className="btn" onClick={clear}>Clear search and filters</button>}>Try a broader search or remove a filter.</EmptyState>
          )}
          {list.status === 'success' && <div className="fdir__grid">{list.data.map(f => <DirectoryCard key={f.id} f={f} />)}</div>}
      </section>
    </div>
  )
}

function DirectoryCard({ f }: { f: FacultyCard }) {
  const [full, setFull] = useState<{ s: 'idle' | 'loading' } | { s: 'error' } | { s: 'done'; bio: string }>({ s: 'idle' })
  const [open, setOpen] = useState(false)
  const truncated = !!f.bio_excerpt && f.bio_excerpt.endsWith('…')
  const toggle = () => {
    if (!open && full.s === 'idle') {
      setFull({ s: 'loading' })
      api.facultyDetail(f.id).then(d => setFull({ s: 'done', bio: d.source.bio ?? '' })).catch(() => setFull({ s: 'error' }))
    }
    setOpen(o => !o)
  }
  return (
    <article className="card fdir__card" style={{ '--c': f.priorities[0] ? PRIORITY_COLORS[f.priorities[0].slug] : 'var(--navy)' } as React.CSSProperties}>
      <Link to={`/faculty/${f.id}`} className="fdir__portrait" aria-label={`Open ${f.name}’s profile`} tabIndex={-1}>
        <Photo src={f.photo_url} name={f.name} className="fdir__photo" />
        {f.directory === 'ysph' && <span className="fdir__tag">YSPH</span>}
        <span className="fdir__school">{f.school}</span>
      </Link>
      <div className="fdir__main">
        <header className="fdir__head">
          <h3><Link to={`/faculty/${f.id}`}>{f.name}</Link></h3>
          <p className="fdir__role">{f.title}</p>
          {f.department && <p className="muted small">{f.department}</p>}
          {f.directory === 'ysph' && <span className="badge badge--source">YSPH · not a YIGH affiliate</span>}
        </header>
        <div className="fdir__prios">
          <span className="fdir__label">YIGH priorities</span>
          {f.priorities.length ? f.priorities.map(p => <PriorityChip key={p.slug} {...p} />) : <span className="muted small">None identified from the profile</span>}
        </div>
        {f.keywords.length > 0 && <div className="chips">{f.keywords.slice(0, 5).map(k => <Chip key={k}>{k}</Chip>)}</div>}
        <p className="fdir__geo small"><span className="fdir__label">Geographic focus</span>
          {f.regions.length ? <>{f.regions.slice(0, 5).join(' · ')}{f.regions.length > 5 && <span className="muted"> +{f.regions.length - 5} more</span>}</>
            : <span className="muted">Not listed on their profile</span>}</p>
        <div className="fdir__bio">
          {!f.bio_excerpt ? <p className="muted small">No biography on the Yale profile.</p>
            : open && full.s === 'done' ? <p>{full.bio}</p>
            : open && full.s === 'loading' ? <p className="muted small">Loading full bio…</p>
            : <p>{f.bio_excerpt}</p>}
          {full.s === 'error' && <p className="small">Couldn’t load the full bio. <a href={`/faculty/${f.id}`}>Open the profile</a>.</p>}
          {truncated && <button className="link-btn small" aria-expanded={open} onClick={toggle}>{open ? 'Show less ▴' : 'Show full bio ▾'}</button>}
        </div>
        <footer className="small fdir__links">
          <Link to={`/faculty/${f.id}`}>Full profile</Link>
          <Link to={`/faculty/${f.id}?collaborators=1`}>Suggested collaborators</Link>
        </footer>
      </div>
    </article>
  )
}
