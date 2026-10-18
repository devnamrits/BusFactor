// Docs one person wrote — shown when they carry no module knowledge.
MATCH (p:Person {id:$person})-[:WROTE]->(d:Doc)
RETURN d.id, d.title
ORDER BY d.id
