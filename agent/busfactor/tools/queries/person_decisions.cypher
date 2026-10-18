// Decisions one person decided — part of the person dossier.
MATCH (d:Decision)-[:DECIDED_BY]->(p:Person {id:$person})
RETURN d.id, d.title
ORDER BY d.id
