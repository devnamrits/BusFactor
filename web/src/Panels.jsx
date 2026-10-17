import { useMemo, useState } from 'react'

const OUTCOME_LABEL = {
  answered_with_path: 'from graph',
  answered_from_memory: 'from memory',
  not_in_graph: 'not in graph',
  unknown_entity: 'unknown entity',
  missing_input: 'needs a run first',
  bad_args: 'bad arguments',
  error: 'error',
}

const SIM_WORDS = {
  drill: 'departure drill',
  heal: 'healed world',
  truth: 'as it is',
}

export function Legend() {
  return (
    <div className="legend">
      <span><i className="sw person" /> person</span>
      <span><i className="sw module" /> module</span>
      <span><i className="sw doc" /> doc</span>
      <span><i className="sw decision" /> decision</span>
      <span><i className="sw bad" /> loss / stranded</span>
      <span><i className="sw plan" /> planned handover</span>
    </div>
  )
}

export function SelectedCard({ node, onAskAbout }) {
  if (!node) return null
  const detail =
    node.label === 'Module'
      ? [node.severity ? `loss severity ${node.severity}` : null, `criticality ${node.criticality}`]
          .filter(Boolean)
          .join(' · ')
      : node.label === 'Person'
        ? node.status === 'departed'
          ? 'departed in this world'
          : 'active'
        : node.label
  // keep the button short — decision titles run long and must never blow out the card
  const action =
    node.label === 'Module'
      ? `who knows ${node.name}?`
      : node.label === 'Person'
        ? `what does ${node.name} carry?`
        : node.label === 'Decision'
          ? 'recall this decision'
          : `recall this ${(node.label || 'node').toLowerCase()}`
  return (
    <div className="selected">
      <div className="sel-head">
        <b>{node.name}</b>
        <span className="badge">{node.label}</span>
      </div>
      <div className="sel-detail">{detail}</div>
      <button className="btn ghost" onClick={() => onAskAbout(node)}>
        {action}
      </button>
    </div>
  )
}

export function AskPanel({ result, busy, suggestions, onAsk, onCite }) {
  const [q, setQ] = useState('')
  const submit = (e) => {
    e?.preventDefault()
    const question = q.trim()
    if (!question) return
    onAsk(question)
    setQ('')
  }
  return (
    <section className="panel">
      <h3>Ask the graph</h3>
      <form className="askform" onSubmit={submit}>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="who can we least afford to lose?"
          spellCheck={false}
        />
        <button className="btn primary" disabled={busy}>
          {busy ? 'running' : 'Ask'}
        </button>
      </form>
      <div className="suggestions">
        {(suggestions || []).map((s) => (
          <button key={s} className="mini" onClick={() => onAsk(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>
      {result && <AnswerCard r={result} onCite={onCite} />}
    </section>
  )
}

function AnswerCard({ r, onCite }) {
  const answered = r.outcome === 'answered_with_path' || r.outcome === 'answered_from_memory'
  return (
    <div className={`answer o-${r.outcome}`}>
      <div className="badges">
        {r.tool && <span className="badge accent">{r.tool}</span>}
        <span className="badge">{OUTCOME_LABEL[r.outcome] || r.outcome}</span>
        {answered &&
          (r.validated ? (
            <span className="badge ok" title="every number is backed by tool data">
              numbers verified
            </span>
          ) : (
            <span className="badge bad" title={r.issues?.join('; ')}>
              unverified
            </span>
          ))}
        <span className="badge">{r.seconds}s</span>
        {r.routing?.engine && (
          <span className="badge" title={r.routing.reason}>
            router: {r.routing.engine}
          </span>
        )}
      </div>
      <p className="answertext">{r.answer}</p>
      {r.citations?.length > 0 && (
        <div className="cites">
          {r.citations.slice(0, 12).map((c, i) =>
            onCite ? (
              <button
                key={i}
                className={`cite k-${c.kind}`}
                title={`${c.detail || c.label} — click to show on the map`}
                onClick={() => onCite(c)}
              >
                {c.label}
              </button>
            ) : (
              <span key={i} className={`cite k-${c.kind}`} title={c.detail || ''}>
                {c.label}
              </span>
            )
          )}
        </div>
      )}
    </div>
  )
}

export function ScenarioPanel({ drill, plan, heal, people, busy, onDrill, onPlan, onHeal }) {
  const active = (people || []).filter((p) => p.status === 'active')
  const [person, setPerson] = useState('')
  const [resilience, setResilience] = useState(true)
  const [showActions, setShowActions] = useState(false)

  const picked = person || active.find((p) => /roi/i.test(p.name))?.name || active[0]?.name || ''

  const resolvedN = Array.isArray(heal?.resolved) ? heal.resolved.length : heal?.resolved
  const remaining = heal?.remaining || []
  const healTotal = (resolvedN || 0) + remaining.length

  return (
    <section className="panel">
      <h3>Departure drill</h3>
      {active.length === 0 ? (
        <p className="empty">No active people in this repo graph yet.</p>
      ) : (
        <div className="row">
          <select value={picked} onChange={(e) => setPerson(e.target.value)}>
            {active.map((p) => (
              <option key={p.id} value={p.name}>
                {p.name} · {p.commits} commits
              </option>
            ))}
          </select>
          <button className="btn primary" disabled={!!busy} onClick={() => onDrill(picked)}>
            {busy === 'drill' ? 'running…' : 'Simulate departure'}
          </button>
        </div>
      )}
      <p className="hint">
        Clones the graph into a throwaway world and removes the person. The real
        snapshot is never touched.
      </p>

      {drill && (
        <div className="box">
          <div className="deltas">
            <Delta label="stranded components" from={drill.before?.islands} to={drill.after?.islands} />
            <Delta label="zero-knower modules" from={drill.before?.zero_modules} to={drill.after?.zero_modules} />
            <Delta label="orphaned decisions" from={drill.before?.orphaned_decisions} to={drill.after?.orphaned_decisions} />
            <Delta label="bus factor" from={drill.before?.bus_factor} to={drill.after?.bus_factor} invert />
          </div>
          <p className="hint">
            world <code>{drill.world}</code> · {drill.seconds}s
          </p>
        </div>
      )}

      {drill && !plan && (
        <div className="box">
          <label className="check">
            <input
              type="checkbox"
              checked={resilience}
              onChange={(e) => setResilience(e.target.checked)}
            />
            also cover modules already down to one knower
          </label>
          <button className="btn primary wide" disabled={!!busy} onClick={() => onPlan(resilience)}>
            {busy === 'plan' ? 'scoring…' : 'Draft handover plan'}
          </button>
        </div>
      )}

      {plan && (
        <div className="box">
          <div className="planmeta">
            <code>{plan.plan_id}</code>
            <span>{plan.counts.steps} steps</span>
            <span>{plan.counts.critical} critical</span>
            <span>{plan.counts.thin} thin</span>
            <span>{plan.counts.resilience} standing fragility</span>
          </div>
          <ol className="steps">
            {plan.steps.map((s) => (
              <li key={s.id} className={`step k-${s.kind}`}>
                <span className="stepmod">{s.module_name}</span>
                <span className="arrow">→</span>
                <span className="stepteacher">{s.teacher_name}</span>
                <span className="why">{s.note}</span>
              </li>
            ))}
          </ol>
          <div className="row">
            <button className="btn ghost" onClick={() => setShowActions((v) => !v)}>
              {showActions ? 'hide payload' : 'preview Actions payload'}
            </button>
            <button className="btn primary" disabled={!!busy} onClick={onHeal}>
              {busy === 'heal' ? 'applying…' : 'Apply & verify'}
            </button>
          </div>
          {showActions && <ActionsPreview plan={plan} />}
        </div>
      )}

      {heal && (
        <div className="box healed">
          <h4>Healed world {heal.world}</h4>
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
          <p className="hint">
            {resolvedN} of {healTotal} drill findings resolved · applied{' '}
            {heal.applied_steps} projected ownership edges · measured in {heal.seconds}s
          </p>
          {remaining.length > 0 && (
            <ul className="remaining">
              {remaining.map((f) => (
                <li key={f.id}>
                  <span className="badge bad">remains</span> {f.claim}
                </li>
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
  const better = invert ? rose : !rose && to !== from
  const worse = invert ? !rose && to !== from : rose
  return (
    <div className={`delta ${better ? 'better' : ''} ${worse ? 'worse' : ''}`}>
      <span className="dl">{label}</span>
      <span className="dv">
        <em>{from}</em> <span className="arrow">→</span> <b>{to}</b>
      </span>
    </div>
  )
}

function ActionsPreview({ plan }) {
  const payload = useMemo(
    () => ({
      repo: 'the repo you configured — never a third-party repo',
      kind: 'handover tracking issue (preview)',
      title: `Handover plan ${plan.plan_id}: ${plan.target?.name} → team`,
      labels: ['knowledge-risk', 'handover'],
      body_markdown: [
        `**Knowledge-risk handover** — ${plan.counts.steps} steps, planned from a measured drill.`,
        '',
        ...plan.steps.map((s) => `- [ ] \`${s.module_name}\` → **${s.teacher_name}** — ${s.note}`),
        '',
        '_Done when the healed world shows 0 stranded components._',
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

export function FindingsPanel({ findings }) {
  const sorted = useMemo(
    () =>
      [...(findings || [])].sort(
        (a, b) => b.severity - a.severity || a.kind.localeCompare(b.kind)
      ),
    [findings]
  )
  if (!sorted.length) {
    return (
      <section className="panel">
        <h3>Findings</h3>
        <p className="empty">No findings in this world. Run a drill to produce them.</p>
      </section>
    )
  }
  return (
    <section className="panel">
      <h3>Findings · {sorted.length}</h3>
      <ul className="findinglist">
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
        {proof && <span className="fproof-hint">{open ? '−' : '+'}</span>}
      </div>
      {open && proof && <pre className="proof">{JSON.stringify(proof, null, 2)}</pre>}
    </li>
  )
}

export function MemoryPanel({ repo, memory, config, onSaveConfig }) {
  const [windowDays, setWindowDays] = useState('')
  const [saved, setSaved] = useState(false)
  const stats = memory?.stats || {}
  const recent = memory?.recent || []
  const ingest = config?.ingest || {}

  const save = async () => {
    const value = parseInt(windowDays || ingest.window_days, 10)
    await onSaveConfig({ window_days: value })
    setWindowDays('')
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  return (
    <>
      <section className="panel">
        <h3>What this instance remembers</h3>
        <div className="statgrid">
          {[
            ['questions', stats.questions],
            ['runs', stats.runs],
            ['findings', stats.findings],
            ['people', stats.people],
            ['modules', stats.modules],
            ['decisions', stats.decisions],
          ].map(([k, v]) => (
            <div key={k} className="stat">
              <b>{v ?? '–'}</b>
              <span>{k}</span>
            </div>
          ))}
        </div>
        <ul className="qlog">
          {recent.slice(0, 14).map((q) => (
            <li key={q.id}>
              <span className={`badge ${q.outcome === 'not_in_graph' ? 'bad' : ''}`}>
                {OUTCOME_LABEL[q.outcome] || q.outcome}
              </span>
              <span className="qtext">{q.text}</span>
            </li>
          ))}
          {recent.length === 0 && <li className="empty">Nothing asked yet.</li>}
        </ul>
      </section>

      <section className="panel">
        <h3>Indexing & runtime</h3>
        <div className="settingrow">
          <span className="k">repo</span>
          <span className="v">
            {repo?.name || repo?.slug}
            {repo?.name && repo?.slug ? ` (${repo.slug})` : ''}
          </span>
        </div>
        <div className="settingrow">
          <span className="k">indexed window</span>
          <span
            className="v"
            title={repo?.meta?.since ? `since ${repo.meta.since.slice(0, 10)}` : ''}
          >
            {repo?.meta?.window_days ?? '–'} days
          </span>
        </div>
        <div className="settingrow">
          <span className="k">default for new repos</span>
          <span className="v">{ingest.window_days ?? '–'} days</span>
        </div>
        <div className="row">
          <input
            type="number"
            min="30"
            max="3650"
            value={windowDays}
            placeholder={String(ingest.window_days ?? 3650)}
            onChange={(e) => setWindowDays(e.target.value)}
          />
          <button className="btn" onClick={save}>
            {saved ? 'saved' : 'set window'}
          </button>
        </div>
        <p className="hint">Applies to the next repo you index.</p>
        <div className="settingrow">
          <span className="k">coverage floor (K)</span>
          <span className="v">{config?.coverage_floor ?? '–'}</span>
        </div>
        <div className="settingrow">
          <span className="k">LLM router</span>
          <span className="v">{config?.llm_router ? 'on' : 'off (deterministic)'}</span>
        </div>
        <div className="settingrow">
          <span className="k">GitHub token</span>
          <span className="v">{config?.github_token ? 'present' : 'absent'}</span>
        </div>
        <p className="hint">
          Set FALKORDB_HOST, GITHUB_TOKEN, LLM_* and COVERAGE_FLOOR in the environment
          (<code>.env</code>); the values above are what this process actually loaded.
        </p>
      </section>
    </>
  )
}

export function Filmstrip({ repo, overview, timeline, world, onWorld }) {
  const sims = timeline?.sims || []
  const summary = overview?.summary
  const entries = [
    {
      world: repo.graph,
      kind: 'truth',
      label: repo.slug,
      metric: summary ? `${summary.modules} modules · bf ${summary.bus_factor}` : '',
    },
    ...sims.map((s) => ({
      world: s.world,
      kind: s.kind,
      label: s.world.replace(/^sim:/, ''),
      metric: `islands ${s.metrics?.islands ?? '?'} · bf ${s.metrics?.bus_factor ?? '?'}`,
      title: s.label,
    })),
  ]
  return (
    <footer className="filmstrip">
      <span className="fs-label">worlds</span>
      <div className="fs-track">
        {entries.map((e) => (
          <button
            key={e.world}
            title={e.title || SIM_WORDS[e.kind]}
            className={`fs-item kind-${e.kind} ${world === e.world ? 'on' : ''}`}
            onClick={() => onWorld(e.world)}
          >
            <span className="fs-kind">{e.kind}</span>
            <span className="fs-label-name">{e.label}</span>
            <span className="fs-met">{e.metric}</span>
          </button>
        ))}
      </div>
    </footer>
  )
}
