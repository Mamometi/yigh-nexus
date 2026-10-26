import type { Confidence } from '../api'

export const PRIORITY_COLORS: Record<string, string> = {
  // Yale web accent colours, chosen to read on white and on the navy network canvas
  'climate-health': '#5f9e3a',
  'digital-health-ai': '#3a8de8',
  'health-diplomacy-security': '#d0702a',
  'health-sovereignty': '#9265c4',
}

export const PRIORITY_SLUGS: Record<string, string> = {
  'Climate & Health': 'climate-health',
  'Digital Health & AI': 'digital-health-ai',
  'Health Diplomacy & Security': 'health-diplomacy-security',
  'Health Sovereignty': 'health-sovereignty',
}

export const CONFIDENCE_HELP =
  'How much of the public profile text supports this tag. More bars means the profile mentions it more clearly. It’s a rough guide, not a score.'

export function Chip({ children, tone = 'default', title }: { children: React.ReactNode; tone?: 'default' | 'accent' | 'muted'; title?: string }) {
  return <span className={`chip chip--${tone}`} title={title}>{children}</span>
}

export function PriorityChip({ name, slug, confidence }: { name: string; slug?: string; confidence?: Confidence }) {
  const color = PRIORITY_COLORS[slug ?? PRIORITY_SLUGS[name]] ?? '#1271e3'
  return (
    <span className="chip chip--priority" style={{ '--c': color } as React.CSSProperties}
          title={confidence ? `${confidence} confidence. ${CONFIDENCE_HELP}` : undefined}>
      <span className="dot" aria-hidden />{name}
      {confidence && <ConfidenceMark level={confidence} />}
    </span>
  )
}

export function CoauthorBadge() {
  return (
    <span className="badge badge--coauthor" title="Listed as frequent co-authors on their Yale profiles (based on publications)">
      ✓ Already co-authors
    </span>
  )
}

export function ConfidenceMark({ level }: { level: Confidence }) {
  const bars = level === 'high' ? 3 : level === 'medium' ? 2 : 1
  return (
    <span className="conf" aria-label={`${level} confidence`} title={`${level} confidence. ${CONFIDENCE_HELP}`}>
      {[1, 2, 3].map(i => <i key={i} className={i <= bars ? 'on' : ''} />)}
    </span>
  )
}
