const J = async (r) => {
  if (!r.ok) {
    let msg = `HTTP ${r.status}`
    try {
      const t = await r.text()
      msg = t.slice(0, 300)
    } catch {}
    throw new Error(msg)
  }
  return r.json()
}

const post = (path, body) =>
  fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then(J)

export const api = {
  health: () => fetch('/api/health').then(J),
  overview: () => fetch('/api/overview').then(J),
  people: () => fetch('/api/people').then(J),
  timeline: () => fetch('/api/timeline').then(J),
  memory: () => fetch('/api/memory').then(J),
  graph: (world) => fetch(`/api/graph?world=${encodeURIComponent(world)}`).then(J),
  findings: (simId) =>
    fetch(`/api/findings?sim_id=${encodeURIComponent(simId || 'latest')}`).then(J),
  ask: (question) => post('/api/ask', { question }),
  drill: (person) => post('/api/drill', { person }),
  plan: (simId) => post('/api/plan', { sim_id: simId || null }),
  heal: (planId) => post('/api/heal', { plan_id: planId || null }),
}
