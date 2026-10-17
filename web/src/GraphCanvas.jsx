import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const LABEL_COLOR = {
  Person: '#2dd4bf',
  Module: '#94a3b8',
  Doc: '#f59e0b',
  Decision: '#a78bfa',
}

function nodeRadius(node) {
  if (node.label === 'Person') return 3.5 + Math.min(5.5, (node.deg || 0) * 0.45)
  if (node.label === 'Module') return 4 + Math.min(6, (node.criticality || 0) * 1.2)
  return 3
}

export default function GraphCanvas({ data, onSelect }) {
  const wrap = useRef(null)
  const fg = useRef(null)
  const [size, setSize] = useState({ w: 900, h: 600 })

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const obs = new ResizeObserver(measure)
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const gdata = useMemo(() => {
    if (!data) return { nodes: [], links: [] }
    const comps = {}
    for (const n of data.nodes) {
      const c = (comps[n.component] = comps[n.component] || { active: false, module: false })
      if (n.label === 'Person' && n.status !== 'departed') c.active = true
      if (n.label === 'Module') c.module = true
    }
    const stranded = new Set()
    for (const [id, v] of Object.entries(comps)) {
      if (v.module && !v.active) stranded.add(Number(id))
    }
    const degree = {}
    for (const l of data.links) {
      degree[l.source] = (degree[l.source] || 0) + 1
      degree[l.target] = (degree[l.target] || 0) + 1
    }
    return {
      nodes: data.nodes.map((n) => ({
        ...n,
        stranded: stranded.has(n.component),
        deg: degree[n.id] || 0,
      })),
      links: data.links.map((l) => ({ ...l })),
    }
  }, [data])

  useEffect(() => {
    const t = setTimeout(() => fg.current?.zoomToFit(600, 60), 400)
    return () => clearTimeout(t)
  }, [data?.world])

  useEffect(() => {
    const f = fg.current
    if (!f) return
    f.d3Force('charge')?.strength(-110)
    f.d3Force('link')?.distance((l) => (l.plan ? 28 : 62))
  }, [gdata])

  const drawNode = (node, ctx, scale) => {
    const r = nodeRadius(node)
    let fill = LABEL_COLOR[node.label] || '#64748b'
    if (node.label === 'Module' && node.severity === 3) fill = '#ef4444'
    else if (node.label === 'Module' && node.severity === 1) fill = '#f59e0b'
    if (node.label === 'Module' && node.stranded) fill = '#ef4444'
    if (node.label === 'Person' && node.status === 'departed') fill = '#334155'

    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = fill
    ctx.globalAlpha = node.label === 'Doc' || node.label === 'Decision' ? 0.8 : 1
    ctx.fill()
    ctx.globalAlpha = 1

    if (node.stranded || (node.label === 'Person' && node.status === 'departed')) {
      ctx.strokeStyle = node.stranded ? '#ef4444' : '#64748b'
      if (node.label === 'Person') ctx.strokeStyle = '#ef4444'
      ctx.lineWidth = 1.4 / scale
      if (node.label === 'Person' && node.status === 'departed') {
        ctx.setLineDash([2.5 / scale, 2 / scale])
      }
      ctx.beginPath()
      ctx.arc(node.x, node.y, r + 2.6 / scale, 0, 2 * Math.PI)
      ctx.stroke()
      ctx.setLineDash([])
    }

    if (scale > 1.15) {
      ctx.font = `${Math.max(2.4, 11 / scale)}px ui-monospace, SFMono-Regular, monospace`
      ctx.textAlign = 'center'
      ctx.fillStyle = 'rgba(203,213,225,0.9)'
      ctx.fillText(node.name, node.x, node.y + r + 9 / scale)
    }
  }

  const linkColor = (l) => {
    if (l.plan) return 'rgba(251,191,36,0.9)'
    if (l.type === 'KNOWS') return 'rgba(45,212,191,0.28)'
    if (l.type === 'OWNS') return 'rgba(148,163,184,0.32)'
    if (l.type === 'DECIDED_BY' || l.type === 'AFFECTS') return 'rgba(167,139,250,0.22)'
    if (l.type === 'WROTE') return 'rgba(245,158,11,0.22)'
    return 'rgba(100,116,139,0.15)'
  }

  const linkWidth = (l) => {
    if (l.plan) return 2
    if (l.type === 'KNOWS') return Math.max(0.5, (l.weight || 0.3) * 1.8)
    return 0.7
  }

  return (
    <div className="canvas" ref={wrap}>
      <ForceGraph2D
        ref={fg}
        graphData={gdata}
        width={size.w}
        height={size.h}
        backgroundColor="#0a0f1c"
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          const r = nodeRadius(node) + 4
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
          ctx.fill()
        }}
        linkColor={linkColor}
        linkWidth={linkWidth}
        onNodeClick={(n) => onSelect && onSelect(n)}
        onBackgroundClick={() => onSelect && onSelect(null)}
        cooldownTicks={140}
      />
    </div>
  )
}
