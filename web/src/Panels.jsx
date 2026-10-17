import { useMemo, useState } from 'react'

const SUGGESTIONS = [
  'Who can we least afford to lose?',
  'What if Roi Lipman leaves?',
  'Who knows src/udf?',
  'What did we decide about graphblas?',
  'Who knows the billing system?',
]

const OUTCOME_LABEL = {
  answered_with_path: 'from graph',
  answered_from_memory: 'from memory',
  not_in_graph: 'not in graph',
  unknown_entity: 'unknown entity',
  missing_input: 'needs a run first',
  bad_args: 'bad arguments',
  error: 'error',
}

export function WorldChips({ timeline, world, onWorld }) {
  const sims = timeline?.sims || []
  const drill = sims.filter((s) => s.kind === 'drill').slice(-1)[0]
  const heal = sims.filter((s) => s.kind === 'heal').slice(-1)[0]
  const chips = [{ world: 'main', label: 'main', metric: 'truth' }]
  if (drill) {
    chips.push({ world: drill.world, label: 'drill', metric: `islands ${drill.metrics?.islands ?? '?'}` })
  }
  if (heal) {
    chips.push({ world: heal.world, label: 'heal', metric: `islands ${heal.metrics?.islands ?? '?'}` })
  }
  return (
    <div className="chips">
      {chips.map((c) => (
        <button
          key={c.world}
          className={`chip ${c.label} ${world === c.world ? 'on' : ''}`}
          onClick={() => onWorld(c.world)}
        >
          <b>{c.label}</b>
          <span>{c.metric}</span>
        </button>
      ))}
    </div>
  )
}

export function AskPanel({ result, busy, onAsk }) {
  const [q, setQ] = useState('')
  const submit = (e) => {
    e?.preventDefault()
    const question = q.trim()
    if (!question) return
    onAsk(question)
    setQ('')
  }
  return (
    <section className="panel ask">
      <h2>Ask</h2>
      <form className="row" onSubmit={submit}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="who can we least afford to lose?"
          spellCheck={false}
        />
        <button disabled={busy}>{busy ? '…' : 'Ask'}</button>
      </form>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="mini" onClick={() => onAsk(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>
      {result && <AnswerCard r={result} />}
    </section>
  )
}

function AnswerCard({ r }) {
  return (
    <div className={`answer o-${r.outcome}`}>
      <div className="badges">
        {r.tool && <span className="badge tool">{r.tool}</span>}
        <span className={`badge outcome o-${r.outcome}`}>
          {OUTCOME_LABEL[r.outcome] || r.outcome}
        </span>
        {r.outcome === 'answered_with_path' || r.outcome === 'answered_from_memory' ? (
          r.validated ? (
            <span className="badge ok" title="every number is backed by tool data">
              ✓ numbers verified
            </span>
          ) : (
            <span className="badge bad" title={r.issues?.join('; ')}>
              numbers unverified
            </span>
          )
        ) : null}
        <span className="badge ghost">{r.seconds}s</span>
        {r.routing?.engine && (
          <span className="badge ghost" title={r.routing.reason}>
            router: {r.routing.engine}
          </span>
        )}
      </div>
      <p className="answertext">{r.answer}</p>
      {r.citations?.length > 0 && (
        <div className="cites">
          {r.citations.slice(0, 12).map((c, i) => (
            <span key={i} className={`cite k-${c.kind}`} title={c.detail || ''}>
              {c.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function PlanPanel({ drill, plan, heal, people, busy, onDrill, onPlan, onHeal }) {
  const [person, setPerson] = useState('Roi Lipman')
  const [showActions, setShowActions] = useState(false)
  const active = (people || []).filter((p) => p.status === 'active')

  const resolvedN = Array.isArray(heal?.resolved) ? heal.resolved.length : heal?.resolved
  const remaining = heal?.remaining || []
  const healTotal = (resolvedN || 0) + remaining.length

  return (
    <section className="panel actor">
      <h2>Act</h2>
      <div className="row">
        <select value={person} onChange={(e) => setPerson(e.target.value)}>
          {active.map((p) => (
            <option key={p.id} value={p.name}>
              {p.name} · {p.commits} commits
            </option>
          ))}
        </select>
        <button disabled={!!busy} onClick={() => onDrill(person)}>
          {busy === 'drill' ? 'drilling…' : 'Simulate departure'}
        </button>
      </div>

      {drill && (
        <div className="box">
          <div className="deltas">
            <Delta label="stranded components" from={drill.before?.islands} to={drill.after?.islands} />
            <Delta label="zero-knower modules" from={drill.before?.zero_modules} to={drill.after?.zero_modules} />
            <Delta label="orphaned decisions" from={drill.before?.orphaned_decisions} to={drill.after?.orphaned_decisions} />
            <Delta label="bus factor" from={drill.before?.bus_factor} to={drill.after?.bus_factor} invert />
          </div>
          <p className="hintline">
            world <code>{drill.world}</code> — main is untouched
          </p>
        </div>
      )}

      {drill && !plan && (
        <button className="wide" disabled={!!busy} onClick={onPlan}>
          {busy === 'plan' ? 'planning…' : 'Build handover plan'}
        </button>
      )}

      {plan && (
        <div className="box">
          <div className="planmeta">
            <code>{plan.plan_id}</code> · {plan.counts.steps} steps · {plan.counts.critical} critical ·{' '}
            {plan.counts.thin} thin · {plan.counts.resilience} standing fragility
          </div>
          <ol className="steps">
            {plan.steps.map((s) => (
              <li key={s.id} className={`step k-${s.kind}`}>
                <span className="stepmod">{s.module_name}</span>
                <span className="arrow">→</span>
                <span className="stepteacher">{s.teacher_name}</span>
                <span className="stepnote">{s.note}</span>
              </li>
            ))}
          </ol>
          <div className="row">
            <button className="ghost" onClick={() => setShowActions((v) => !v)}>
              {showActions ? 'Hide preview' : 'Preview Actions run'}
            </button>
            <button disabled={!!busy} onClick={onHeal}>
              {busy === 'heal' ? 'healing…' : 'Heal & verify'}
            </button>
          </div>
          {showActions && <ActionsPreview plan={plan} />}
        </div>
      )}

      {heal && (
        <div className="box healbox">
          <div className="deltas">
            <Delta
              label="stranded components"
              from={heal.drill?.islands ?? heal.before?.islands}
              to={heal.after?.islands}
            />
            <Delta
              label="zero-knower modules"
              from={heal.drill?.zero_modules ?? heal.before?.zero_modules}
              to={heal.after?.zero_modules}
            />
            <Delta
              label="bus factor"
              from={heal.drill?.bus_factor ?? heal.before?.bus_factor}
              to={heal.after?.bus_factor}
              invert
            />
          </div>
          <p className="hintline">
            {resolvedN} of {healTotal} drill findings resolved · applied {heal.applied_steps} projected
            ownership edges
          </p>
          {remaining.length > 0 && (
            <ul className="remaining">
              {remaining.map((f) => (
                <li key={f.id}>{f.claim}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function Delta({ label, from, to, invert }) {
  if (from === undefined || to === undefined) return null
  const rose = to > from
  const good = invert ? rose : !rose && to !== from
  const bad = invert ? !rose && to !== from : rose
  return (
    <div className={`delta ${good ? 'better' : ''} ${bad ? 'worse' : ''}`}>
      <span className="dl">{label}</span>
      <span className="dv">
        {from} <span className="arrow">→</span> {to}
      </span>
    </div>
  )
}

function ActionsPreview({ plan }) {
  const payload = useMemo(
    () => ({
      repo: 'configured repo only — never third-party',
      kind: 'handover tracking issue (preview)',
      title: `Handover plan ${plan.plan_id}: ${plan.target?.name} → team`,
      labels: ['knowledge-risk', 'handover'],
      body_markdown: [
        `**Knowledge-risk handover** — ${plan.counts.steps} steps, planned from a measured drill.`,
        '',
        ...plan.steps.map((s) => `- [ ] \`${s.module_name}\` → **${s.teacher_name}** — ${s.note}`),
        '',
        '_Done when `heal_and_verify` shows the drilled scenario back at 0 stranded components._',
      ].join('\n'),
    }),
    [plan]
  )
  return (
    <div className="payload">
      <span className="badge">preview only — nothing is opened</span>
      <pre>{JSON.stringify(payload, null, 2)}</pre>
    </div>
  )
}

export function FindingsCard({ findings }) {
  if (!findings?.length) return null
  const sorted = [...findings].sort(
    (a, b) => b.severity - a.severity || a.kind.localeCompare(b.kind)
  )
  return (
    <section className="panel findings">
      <h2>
        Findings <span className="count">{findings.length}</span>
      </h2>
      <ul>
        {sorted.map((f) => (
          <FindingItem key={f.id} f={f} />
        ))}
      </ul>
    </section>
  )
}

function FindingItem({ f }) {
  const [open, setOpen] = useState(false)
  const proof = f.proof && Object.keys(f.proof).length > 0 ? f.proof : null
  return (
    <li className={`finding sev-${f.severity}`} onClick={() => setOpen((v) => !v)}>
      <div className="fline">
        <span className={`sev s${f.severity}`}>S{f.severity}</span>
        <span className="fkind">{(f.kind || '').replaceAll('_', ' ')}</span>
        <span className="fclaim">{f.claim}</span>
      </div>
      {open && proof && <pre className="proof">{JSON.stringify(proof, null, 2)}</pre>}
    </li>
  )
}

export function TimelineBar({ timeline, world, onWorld }) {
  const sims = timeline?.sims || []
  return (
    <footer className="timeline">
      <span className="tlabel">worlds</span>
      <button className={`tchip main ${world === 'main' ? 'on' : ''}`} onClick={() => onWorld('main')}>
        <b>main</b>
        <span>truth · everything as it is</span>
      </button>
      {sims.map((s) => (
        <button
          key={s.id}
          className={`tchip ${s.kind} ${world === s.world ? 'on' : ''}`}
          onClick={() => onWorld(s.world)}
        >
          <b>{s.kind}</b>
          <span>
            {s.label} · islands {s.metrics?.islands ?? '?'} · bus {s.metrics?.bus_factor ?? '?'}
          </span>
        </button>
      ))}
    </footer>
  )
}

export function Legend() {
  return (
    <div className="legend">
      <span>
        <i style={{ background: '#2dd4bf' }} /> person
      </span>
      <span>
        <i style={{ background: '#94a3b8' }} /> module
      </span>
      <span>
        <i style={{ background: '#f59e0b' }} /> doc
      </span>
      <span>
        <i style={{ background: '#a78bfa' }} /> decision
      </span>
      <span>
        <i style={{ background: '#ef4444' }} /> loss / stranded
      </span>
      <span>
        <i style={{ background: '#fbbf24' }} /> planned handover
      </span>
    </div>
  )
}

export function SelectedCard({ node, onAskAbout }) {
  if (!node) return null
  const detail =
    node.label === 'Module'
      ? `${node.severity ? `loss severity ${node.severity} · ` : ''}criticality ${node.criticality}`
      : node.label === 'Person'
        ? node.status === 'departed'
          ? 'departed (in this world)'
          : 'active'
        : node.label
  return (
    <div className="selected">
      <div>
        <b>{node.name}</b> <span className="badge ghost">{node.label}</span>
      </div>
      <div className="detail">{detail}</div>
      <button
        onClick={() =>
          onAskAbout(
            node.label === 'Module'
              ? `who knows ${node.name}?`
              : node.label === 'Person'
                ? `what does ${node.name} carry?`
                : `${node.name}`
          )
        }
      >
        {node.label === 'Module'
          ? `who knows ${node.name}?`
          : node.label === 'Person'
            ? `what does ${node.name} carry?`
            : `ask about ${node.name}`}
      </button>
    </div>
  )
}
