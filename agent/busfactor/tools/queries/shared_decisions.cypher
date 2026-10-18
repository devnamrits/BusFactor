// Decisions both people signed.
MATCH (d:Decision)-[:DECIDED_BY]->(a:Person {id:$a}), (d)-[:DECIDED_BY]->(b:Person {id:$b})
RETURN d.id, d.title, d.decided_at
ORDER BY d.decided_at DESC
LIMIT 5
