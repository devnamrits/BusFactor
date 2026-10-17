import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import GraphCanvas from './GraphCanvas.jsx'
import {
  AskPanel,
  FindingsCard,
  Legend,
  PlanPanel,
  SelectedCard,
  TimelineBar,
  WorldChips,
} from './Panels.jsx'

export default function App() {
  const [health, setHealth] = useState(null)
  const [people, setPeople] = useState([])
  const [overview, setOverview] = useState(null)
  const [timeline, setTimeline] = useState({ sims: [], plans: [] })
  const [graph, setGraph] = useState(null)
  const [world, setWorld] = useState('main')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [askResult, setAskResult] = useState(null)
  const [drill, setDrill] = useState(null)
  const [plan, setPlan] = useState(null)
  const [heal, setHeal] = useState(null)
  const [selected, setSelected] = useState(null)

  const refreshTimeline = useCallback(async () => {
    setTimeline(await api.timeline())
  }, [])

  const loadWorld = useCallback(async (w) => {
    setWorld(w)
    setGraph(await api.graph(w))
    setSelected(null)
  }, [])

  const refreshOverview = useCallback(async () => {
    setOverview(await api.overview())
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const [h, p, o, t] = await Promise.all([
          api.health(),
          api.people(),
          api.overview(),
          api.timeline(),
        ])
        setHealth(h)
        setPeople(p)
        setOverview(o)
        setTimeline(t)
        await loadWorld('main')
      } catch (e) {
        setError(String(e.message || e))
      }
    })()
  }, [loadWorld])

  const guard = async (tag, fn) => {
    setBusy(tag)
    setError('')
    try {
      await fn()
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy('')
    }
  }

  const runAsk = (question) =>
    guard('ask', async () => {
      const r = await api.ask(question)
      setAskResult(r)
      const d = r.data || {}
      if (r.tool === 'simulate_departure' && d.world) {
        setDrill({ ...d, sim_id: d.sim_id, findings: d.findings || [] })
        setPlan(null)
        setHeal(null)
        await loadWorld(d.world)
        await refreshTimeline()
      } else if (r.tool === 'handover_plan' && d.plan_id) {
        setPlan(d)
      } else if (r.tool === 'heal_and_verify' && d.world) {
        setHeal(d)
        await loadWorld(d.world)
        await refreshTimeline()
        await refreshOverview()
      } else if (r.tool === 'critical_people') {
        await refreshOverview()
      }
    })

  const runDrill = (person) =>
    guard('drill', async () => {
      const d = await api.drill(person)
      setDrill(d)
      setPlan(null)
      setHeal(null)
      await loadWorld(d.world)
      await refreshTimeline()
    })

  const runPlan = () =>
    guard('plan', async () => {
      const p = await api.plan(drill?.sim_id)
      setPlan(p)
      await refreshTimeline()
    })

  const runHeal = () =>
    guard('heal', async () => {
      const h = await api.heal(plan?.plan_id)
      setHeal(h)
      await loadWorld(h.world)
      await refreshTimeline()
      await refreshOverview()
    })

  const askAboutNode = (node) => {
    if (!node) return
    if (node.label === 'Module') runAsk(`who knows ${node.name}?`)
    else if (node.label === 'Person') runAsk(`what does ${node.name} carry?`)
    else if (node.label === 'Decision') runAsk(node.name)
    else runAsk(node.name)
  }

  const mem = overview?.memory?.stats
  const findings =
    drill && drill.world === world ? drill.findings : graph?.findings || []

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◉</span> BusFactor
          <span className="tagline">know who your team can’t lose</span>
        </div>
        <WorldChips timeline={timeline} world={world} onWorld={loadWorld} />
        <div className="statline">
          {health?.ok ? <span className="dot ok" /> : <span className="dot bad" />}
          <span>
            {health?.nodes ?? '…'} nodes · {health?.edges ?? '…'} edges · snap{' '}
            <code>{health?.snapshot_sha || '…'}</code>
          </span>
          {mem && (
            <span className="memchip" title="memory: questions remembered">
              🧠 {mem.questions} asked · {mem.runs} runs
            </span>
          )}
        </div>
      </header>

      {error && <div className="errorbar">{error}</div>}

      <main>
        <section className="canvas-wrap">
          <GraphCanvas data={graph} onSelect={setSelected} />
          <Legend />
          <SelectedCard node={selected} onAskAbout={askAboutNode} />
          <div className="worldbadge">
            world <code>{world}</code>
          </div>
        </section>

        <aside className="side">
          <AskPanel result={askResult} busy={busy === 'ask'} onAsk={runAsk} />
          <PlanPanel
            drill={drill}
            plan={plan}
            heal={heal}
            people={people}
            busy={busy}
            onDrill={runDrill}
            onPlan={runPlan}
            onHeal={runHeal}
          />
          <FindingsCard findings={findings} />
        </aside>
      </main>

      <TimelineBar timeline={timeline} world={world} onWorld={loadWorld} />
    </div>
  )
}
