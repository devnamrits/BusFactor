// Every recorded decision, with who decided it and what it touched.
MATCH (d:Decision)
OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person)
OPTIONAL MATCH (d)-[:AFFECTS]->(m:Module)
RETURN d.id, d.title, d.decided_at, d.source_ref,
       collect(DISTINCT p.name) AS deciders, collect(DISTINCT m.name) AS modules
ORDER BY d.decided_at DESC
