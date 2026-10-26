import { useEffect, useRef, useState } from 'react'
import { Photo } from '../components/Photo'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type GeneratedTag } from '../api'
import { Collaborators } from '../components/Collaborators'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { CONFIDENCE_HELP, Chip, ConfidenceMark, PriorityChip } from '../components/Tags'
import { useAsync } from '../hooks'

export function Profile() {
  const id = Number(useParams().id)
  const [params, setParams] = useSearchParams()
  const showCollab = params.get('collaborators') === '1'
  const [state, retry] = useAsync(() => api.facultyDetail(id), [id])
  const collabRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (showCollab && state.status === 'success') collabRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [showCollab, state.status, id])

  if (!Number.isInteger(id)) return <EmptyState title="Profile not found" action={<Link className="btn" to="/">Back to directory</Link>} />
  if (state.status === 'loading') return <Loading label="Loading profile…" />
  if (state.status === 'error') return (
    <div className="page"><Link to="/" className="back">← Directory</Link><ErrorState message={state.error} onRetry={retry} /></div>
  )
  const f = state.data
  const g = f.generated

  return (
    <div className="page profile">
      <Link to="/" className="back">← Back to directory</Link>

      <header className="profile__head card">
        <Photo src={f.photo_url} name={f.name} className="photo--profile" />
        <div className="profile__id">
          <h1>{f.name}</h1>
          {f.title && <p className="profile__title">{f.title}</p>}
          <p className="muted">{[f.school && `School of ${f.school === 'University' ? 'University (other Yale schools)' : f.school}`, f.department].filter(Boolean).join(' · ')}</p>
          <div className="profile__links small">
            {f.email && <a href={`mailto:${f.email}`}>✉ {f.email}</a>}
            <a href={f.profile_url} target="_blank" rel="noreferrer">Yale profile ↗</a>
          </div>
        </div>
        <button className="btn btn--lg" onClick={() => { setParams({ collaborators: '1' }); collabRef.current?.scrollIntoView({ behavior: 'smooth' }) }}>
          ✦ Find collaborators
        </button>
      </header>

      <div className="profile__cols">
        <section className="card">
          <h2>About</h2>
          <p className="source-label small">From the public Yale profile</p>
          {f.directory === 'ysph' && f.inclusion_reasons.length > 0 && (
            <div className="why small">
              <strong>Why this person is in Constellation:</strong> they are in the YSPH faculty directory (not a YIGH affiliate) and their profile describes global health work:
              <ul className="plain">{f.inclusion_reasons.map(r => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
          {f.source.bio ? <p className="bio">{f.source.bio}</p> : <p className="muted">This profile has no biography.</p>}
          {f.source.research_interests.length > 0 && (<>
            <h3>Research interests listed on the profile</h3>
            <div className="chips">{f.source.research_interests.map(i => <Chip key={i} tone="muted">{i}</Chip>)}</div>
          </>)}
          {f.source.activities.length > 0 && (<>
            <h3>International &amp; research activities</h3>
            <ul className="activities">
              {f.source.activities.map((a, i) => (
                <li key={i}>
                  <strong>{a.title}</strong>
                  <p className="muted small">{[a.type, formatRange(a.start, a.end)].filter(Boolean).join(' · ')}</p>
                  {a.locations.length > 0 && <p className="small">◎ {a.locations.join('; ')}</p>}
                  {a.synopsis && <p className="small">{a.synopsis}</p>}
                </li>
              ))}
            </ul>
          </>)}
          {f.source.yale_coauthors.length > 0 && (<>
            <h3>Yale co-authors</h3>
            <p className="muted small">Frequent collaborators on published research, as listed on the Yale profile.</p>
            <div className="chips">
              {f.source.yale_coauthors.map(c => c.faculty_id
                ? <Link key={c.name} className="chip chip--link" to={`/faculty/${c.faculty_id}`}>{c.name}</Link>
                : <a key={c.name} className="chip chip--link" href={c.profile_url ?? '#'} target="_blank" rel="noreferrer">{c.name} ↗</a>)}
            </div>
          </>)}
          {f.source.organizations.length > 0 && (<>
            <h3>Other departments &amp; organizations</h3>
            <div className="chips">
              {f.source.organizations.map(o => o.url
                ? <a key={o.name} className="chip chip--link" href={o.url} target="_blank" rel="noreferrer">{o.name}</a>
                : <Chip key={o.name} tone="muted">{o.name}</Chip>)}
            </div>
          </>)}
          {f.source.appointments.length > 0 && (<>
            <h3>Appointments</h3>
            <ul className="plain">{f.source.appointments.map((a, i) => <li key={i}>{a.title} · {a.department}{a.type ? <span className="muted"> ({a.type})</span> : null}</li>)}</ul>
          </>)}
        </section>

        <section className="card">
          <h2>How Constellation reads this profile</h2>
          <p className="source-label small">Tagged automatically from the profile text. Select a tag to see why. <span title={CONFIDENCE_HELP} className="help">What do the bars mean?</span></p>
          <TagGroup title="YIGH strategic priorities" tags={g.priorities} empty="No priority could be identified from the profile text." priority />
          <TagGroup title="Research areas" tags={g.keywords} empty="No standard research areas identified." />
          <TagGroup title="Geographic focus" tags={g.regions} empty="No place is explicitly tied to their research in the profile." />
        </section>
      </div>

      <div ref={collabRef}>
        {showCollab ? <Collaborators facultyId={f.id} name={f.name} /> : (
          <section className="collab collab--cta card">
            <h2>Looking for a research partner?</h2>
            <p className="muted">See faculty whose work overlaps with or complements {f.name.split(',')[0]}’s, with the reasons for each suggestion.</p>
            <button className="btn btn--lg" onClick={() => setParams({ collaborators: '1' })}>✦ Find collaborators</button>
          </section>
        )}
      </div>
    </div>
  )
}

function formatRange(start: string | null, end: string | null) {
  const fmt = (d: string | null) => (d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : null)
  if (!start && !end) return null
  return `${fmt(start) ?? '?'} – ${fmt(end) ?? 'present'}`
}

function TagGroup({ title, tags, empty, priority }: { title: string; tags: GeneratedTag[]; empty: string; priority?: boolean }) {
  const [open, setOpen] = useState<string | null>(null)
  const selected = tags.find(t => t.name === open)
  return (
    <div className="tag-group">
      <h3>{title}</h3>
      {tags.length === 0 ? <p className="muted small">{empty}</p> : (
        <div className="chips">
          {tags.map(t => (
            <button key={t.name} className={`tag-btn ${open === t.name ? 'is-on' : ''}`} aria-expanded={open === t.name}
                    onClick={() => setOpen(o => (o === t.name ? null : t.name))}>
              {priority ? <PriorityChip name={t.name} confidence={t.confidence} />
                : <span className="chip">{t.name}<ConfidenceMark level={t.confidence} /></span>}
            </button>
          ))}
        </div>
      )}
      {selected && (
        <div className="why">
          <p><strong>Why “{selected.name}”?</strong> {selected.explanation}</p>
          {selected.evidence.slice(0, 3).map((e, i) => e.snippet && (
            <blockquote key={i}><cite>{e.field.replace('_', ' ')}:</cite> “{e.snippet}”</blockquote>
          ))}
        </div>
      )}
    </div>
  )
}
