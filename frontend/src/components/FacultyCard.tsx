import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FacultyCard as Card, type FacultyDetail } from '../api'
import { Chip, PriorityChip } from './Tags'

export function initials(name: string) {
  const parts = name.split(',')[0].trim().split(/\s+/)
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

type BioState = { status: 'idle' | 'loading' } | { status: 'error'; error: string } | { status: 'ready'; data: FacultyDetail }

export function FacultyCard({ f }: { f: Card }) {
  const [open, setOpen] = useState(false)
  const [bio, setBio] = useState<BioState>({ status: 'idle' })
  const panelId = useId()

  // The bio is fetched the first time the card is expanded, then kept.
  const load = () => {
    setBio({ status: 'loading' })
    api.facultyDetail(f.id)
      .then(data => setBio({ status: 'ready', data }))
      .catch((e: Error) => setBio({ status: 'error', error: e.message }))
  }
  const toggle = () => {
    if (!open && bio.status === 'idle') load()
    setOpen(o => !o)
  }

  return (
    <article className={`card faculty-card ${open ? 'is-open' : ''}`}>
      <div className="faculty-card__body">
        <header className="faculty-card__head">
          <div className="avatar" aria-hidden>{initials(f.name)}</div>
          <div>
            <h3>{f.name}</h3>
            <p className="muted small">{[f.school, f.department].filter(Boolean).join(' · ') || 'School not listed'}</p>
            {f.directory === 'ysph' && <span className="badge badge--source" title="Found in the YSPH faculty directory; not listed as a YIGH affiliate">YSPH · not a YIGH affiliate</span>}
          </div>
        </header>
        {f.title && <p className="faculty-card__title">{f.title}</p>}
        {f.priorities.length > 0 && (
          <div className="chips">{f.priorities.map(p => <PriorityChip key={p.slug} {...p} />)}</div>
        )}
        {f.keywords.length > 0 ? (
          <div className="chips">{f.keywords.slice(0, 4).map(k => <Chip key={k}>{k}</Chip>)}
            {f.keywords.length > 4 && <Chip tone="muted">+{f.keywords.length - 4}</Chip>}</div>
        ) : <p className="muted small">No research areas could be identified from this profile.</p>}
        {f.regions.length > 0 && (
          <p className="faculty-card__geo small"><span aria-hidden>◎</span> {f.regions.slice(0, 3).join(', ')}{f.regions.length > 3 ? ` +${f.regions.length - 3}` : ''}</p>
        )}
      </div>

      {open && (
        <div id={panelId} className="faculty-card__bio" role="region" aria-label={`Biography of ${f.name}`}>
          {bio.status === 'loading' && <p className="muted small"><span className="spinner spinner--sm" aria-hidden /> Loading bio…</p>}
          {bio.status === 'error' && (
            <p className="small">Couldn’t load the bio. <button className="link-btn" onClick={load}>Try again</button></p>
          )}
          {bio.status === 'ready' && (
            <>
              {bio.data.source.bio
                ? <p className="faculty-card__bio-text">{bio.data.source.bio}</p>
                : <p className="muted small">This faculty member has no biography on their Yale profile.</p>}
              {bio.data.source.activities.some(a => a.locations.length) && (
                <p className="small"><strong>Activity locations:</strong>{' '}
                  {[...new Set(bio.data.source.activities.flatMap(a => a.locations))].slice(0, 4).join('; ')}</p>
              )}
              <p className="small faculty-card__bio-links">
                {bio.data.email && <a href={`mailto:${bio.data.email}`}>✉ {bio.data.email}</a>}
                <Link to={`/faculty/${f.id}`}>Full profile</Link>
              </p>
            </>
          )}
        </div>
      )}

      <footer className="faculty-card__foot">
        <button className="btn btn--ghost btn--sm" onClick={toggle} aria-expanded={open} aria-controls={panelId}>
          {open ? 'Hide bio ▴' : 'Show bio ▾'}
        </button>
        <Link to={`/faculty/${f.id}?collaborators=1`} className="btn btn--sm">Find collaborators</Link>
      </footer>
    </article>
  )
}
