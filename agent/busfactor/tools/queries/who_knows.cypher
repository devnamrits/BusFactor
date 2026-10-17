// Who knows a module best? Ranked by KNOWS weight; PR citations attached.
MATCH (p:Person {status:'active'})-[k:KNOWS]->(m:Module {id:$module})
OPTIONAL MATCH (p)-[:AUTHORED]->(pr:PR)-[:TOUCHES]->(m)
WITH p, k, collect(DISTINCT pr.number) AS prs
RETURN p.id, p.name, k.weight, k.commits, k.reviews, k.last_at, prs
ORDER BY k.weight DESC, p.id
LIMIT 5
