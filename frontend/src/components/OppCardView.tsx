import { Link } from 'react-router-dom'
import type { OppCard } from '../api'
import { PriorityChip } from './Tags'

export const fmtDate = (d?: string | null) =>
  d ? new Date(d + (d.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : null

export const VERIFY_LABEL: Record<string, string> = {
  verified: 'Checked with the funder', partially_verified: 'Partly checked with the funder',
  unverified: 'Not checked yet', mismatch: 'Details don’t match the funder’s page',
}

export function Deadline({ o }: { o: OppCard }) {
  if (o.status === 'closed') return <span className="deadline deadline--closed">Closed</span>
  if (!o.deadline) return <span className="deadline">{o.deadline_text ?? 'No deadline stated'}</span>
  const urgent = o.days_left !== null && o.days_left <= 30
  return (
    <span className={`deadline ${urgent ? 'deadline--soon' : ''}`}>
      {o.status === 'forecasted' ? 'Est. ' : ''}{fmtDate(o.deadline)}
      {o.days_left !== null && <em> · {o.days_left} days left</em>}
    </span>
  )
}

export function OppCardView({ o }: { o: OppCard }) {
  return (
    <article className="card opp-card">
      <div className="opp-card__top">
        <span className={`status status--${o.status}`}>{o.status}</span>
        <Deadline o={o} />
      </div>
      <h3><Link to={`/radar/${o.id}`}>{o.title}</Link></h3>
      <p className="muted small">{[o.funder, o.opportunity_number].filter(Boolean).join(' · ')}</p>
      {o.award_text && <p className="small"><strong>Award:</strong> {o.award_text}</p>}
      {o.priorities.length > 0 && <div className="chips">{o.priorities.map(p => <PriorityChip key={p.slug} name={p.name} slug={p.slug} confidence={p.confidence} />)}</div>}
      <div className="opp-card__foot">
        <span className={`verify verify--${o.verification_status}`} title="We compare each listing with the funder's own page">
          {VERIFY_LABEL[o.verification_status] ?? o.verification_status}{o.needs_review ? ' · needs review' : ''}
        </span>
        <span className="opp-card__actions">
          <a className="small" href={o.official_url} target="_blank" rel="noreferrer">Official source ↗</a>
          <Link className="btn btn--sm" to={`/radar/${o.id}#team`}>Find a team</Link>
        </span>
      </div>
    </article>
  )
}
