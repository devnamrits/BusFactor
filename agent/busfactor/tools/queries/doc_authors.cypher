// Who wrote a doc page.
MATCH (p:Person)-[:WROTE]->(d:Doc {id:$doc})
RETURN p.id, p.name
ORDER BY p.name
