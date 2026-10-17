// Knowledge mass per active person: how much of the codebase depends on them.
MATCH (p:Person {status:'active'})
OPTIONAL MATCH (p)-[k:KNOWS]->(m:Module)
WITH p, collect(DISTINCT m.id) AS mids, sum(k.weight) AS mass
RETURN p.id, p.name, p.commits, mids, mass
