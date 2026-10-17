// Decisions attached to one module.
MATCH (d:Decision)-[:AFFECTS]->(m:Module {id:$module})
OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person)
RETURN d.id, d.title, d.source_ref, collect(DISTINCT p.name)
