// Coverage and criticality for one module.
MATCH (m:Module {id:$module})
OPTIONAL MATCH (p:Person {status:'active'})-[:KNOWS|OWNS]->(m)
WITH m, collect(DISTINCT p.name) AS knowers
RETURN m.id, m.name, m.path, m.commits_window, m.criticality, knowers
