import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Criterion, Match } from '../api'
import { Chip, CoauthorBadge, PriorityChip } from './Tags'

export const CRITERION_LABELS: Record<Criterion, string> = {
  shared_interests: 'Shared research',
  complementary_expertise: 'Complementary expertise',
  geography: 'Places in common',
  strategic_priorities: 'YIGH priorities',
  cross_school: 'Across schools',
}

export function fitLabel(score: number) {
  return score >= 0.6 ? 'Strong fit' : score >= 0.45 ? 'Good fit' : 'Possible fit'
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const C = 2 * Math.PI * 26
  return (
    <div className="score" aria-label={`Compatibility ${pct} out of 100, ${fitLabel(score)}`}>
      <svg viewBox="0 0 64 64" aria-hidden>
        <circle cx="32" cy="32" r="26" className="score__track" />
        <circle cx="32" cy="32" r="26" className="score__bar" strokeDasharray={`${C * score} ${C}`} />
      </svg>
      <span className="score__num">{pct}</span>
    </div>
  )
}

export function MatchCard({ m, selfName }: { m: Match; selfName: string }) {
  const [open, setOpen] = useState(false)
  const h = m.highlights
  const other = m.faculty
  return (
    <article className="card match">
      <div className="match__rank" aria-label={`Rank ${m.rank}`}>{m.rank}</div>
      <div className="match__main">
        <header className="match__head">
          <div>
            <h3><Link to={`/faculty/${other.id}`}>{other.name}</Link></h3>
            <p className="muted small">{[other.school, other.departments[0]].filter(Boolean).join(' · ')}</p>
            {m.already_coauthors && <CoauthorBadge />}
          </div>
          <div className="match__score">
            <ScoreRing score={m.score} />
            <span className={`fit fit--${fitLabel(m.score).split(' ')[0].toLowerCase()}`}>{fitLabel(m.score)}</span>
          </div>
        </header>

        <p className="match__why"><strong>Why this pairing: </strong>{m.summary}</p>

        <div className="match__facets">
          <Facet title="Overlapping interests" empty="No directly shared topics. This suggestion rests on complementary skills or shared context.">
            {h.shared_interests.slice(0, 6).map(t => <Chip key={t} tone="accent">{t}</Chip>)}
          </Facet>
          <Facet title="Complementary expertise" empty="None identified from the profiles.">
            {h.complementary_expertise.slice(0, 4).map(t => <Chip key={t}>{t}</Chip>)}
          </Facet>
          {(h.strategic_priorities.length > 0 || h.geography.length > 0) && (
            <Facet title="Also in common">
              {h.strategic_priorities.map(p => <PriorityChip key={p} name={p} />)}
              {h.geography.map(g => <Chip key={g}>◎ {g}</Chip>)}
            </Facet>
          )}
        </div>

        <button className="link-btn" aria-expanded={open} onClick={() => setOpen(o => !o)}>
          {open ? 'Hide details' : 'Why this suggestion?'}
        </button>
        {open && (
          <div className="match__details">
            <h4>Score breakdown</h4>
            <ul className="bars">
              {(Object.keys(m.breakdown) as Criterion[]).map(c => (
                <li key={c}>
                  <span>{CRITERION_LABELS[c]}</span>
                  <span className="bar"><span style={{ width: `${m.breakdown[c].score * 100}%` }} /></span>
                  <span className="muted small">{Math.round(m.breakdown[c].contribution * 100)} pts</span>
                </li>
              ))}
            </ul>
            <p className="muted small">Each bar shows how strongly that factor applies. Points are that factor's share of the {Math.round(m.score * 100)}-point total, after weighting.</p>
            <h4>From their profiles</h4>
            <ul className="reasons">
              {m.reasons.map((r, i) => (
                <li key={i}>
                  <span className="reasons__tag">{CRITERION_LABELS[r.criterion]}</span> {r.text}
                  {r.evidence.filter(e => e.text).map((e, j) => (
                    <blockquote key={j}><cite>{e.faculty_id === other.id ? other.name : selfName}, {e.field?.replace('_', ' ') ?? 'profile'}:</cite> “{e.text}”</blockquote>
                  ))}
                </li>
              ))}
            </ul>
            <a className="small" href={other.profile_url} target="_blank" rel="noreferrer">Read {other.name.split(',')[0]}’s full Yale profile ↗</a>
          </div>
        )}
      </div>
    </article>
  )
}

function Facet({ title, empty, children }: { title: string; empty?: string; children?: React.ReactNode[] | React.ReactNode }) {
  const items = Array.isArray(children) ? children.flat().filter(Boolean) : children ? [children] : []
  return (
    <div className="facet">
      <h4>{title}</h4>
      {items.length ? <div className="chips">{items}</div> : <p className="muted small">{empty}</p>}
    </div>
  )
}
