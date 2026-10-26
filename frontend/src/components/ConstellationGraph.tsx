import { useNavigate } from 'react-router-dom'
import type { Match } from '../api'
import { initials } from './FacultyCard'

/** Star-map view: the selected person in the centre, closer = stronger fit. */
export function ConstellationGraph({ center, matches }: { center: string; matches: Match[] }) {
  const navigate = useNavigate()
  const W = 520, H = 360, cx = W / 2, cy = H / 2
  const shown = matches.slice(0, 12)
  const hi = Math.max(...shown.map(m => m.score)), lo = Math.min(...shown.map(m => m.score))
  const nodes = shown.map((m, i, arr) => {
    const angle = (i / arr.length) * Math.PI * 2 - Math.PI / 2
    // Distance is relative to the scores shown, so differences stay visible.
    const rel = hi === lo ? 0 : (hi - m.score) / (hi - lo)
    const r = 70 + rel * 110
    return { m, x: cx + Math.cos(angle) * r * 1.25, y: cy + Math.sin(angle) * r * 0.82 }
  })
  return (
    <figure className="graph">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Map of ${nodes.length} suggested collaborators around ${center}; closer means a stronger fit`}>
        <defs>
          <radialGradient id="glow"><stop offset="0%" stopColor="#b4e7f8" stopOpacity=".55" /><stop offset="100%" stopColor="#b4e7f8" stopOpacity="0" /></radialGradient>
        </defs>
        {[90, 160, 230].map(r => <ellipse key={r} cx={cx} cy={cy} rx={r * 1.25} ry={r * 0.82} className="graph__ring" />)}
        {nodes.map(({ m, x, y }) => (
          <line key={`l${m.faculty.id}`} x1={cx} y1={cy} x2={x} y2={y} className="graph__edge"
                style={{ strokeOpacity: 0.2 + m.score * 0.7, strokeWidth: 0.6 + m.score * 2 }} />
        ))}
        <circle cx={cx} cy={cy} r={46} fill="url(#glow)" />
        <circle cx={cx} cy={cy} r={20} className="graph__center" />
        <text x={cx} y={cy + 4} className="graph__initials">{initials(center)}</text>
        {nodes.map(({ m, x, y }) => (
          <g key={m.faculty.id} className="graph__node" tabIndex={0} role="link"
             onClick={() => navigate(`/faculty/${m.faculty.id}`)}
             onKeyDown={e => e.key === 'Enter' && navigate(`/faculty/${m.faculty.id}`)}>
            <title>{`#${m.rank} ${m.faculty.name} — ${Math.round(m.score * 100)}`}</title>
            <circle cx={x} cy={y} r={8 + m.score * 10} />
            <text x={x} y={y + 3.5} className="graph__rank">{m.rank}</text>
            <text x={x} y={y + 24 + m.score * 8} className="graph__label">{m.faculty.name.split(',')[0]}</text>
          </g>
        ))}
      </svg>
      <figcaption className="muted small">Closer to the centre = stronger suggested fit. Click a star to open that profile.</figcaption>
    </figure>
  )
}
