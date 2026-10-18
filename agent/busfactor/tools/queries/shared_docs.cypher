// Docs both people wrote.
MATCH (a:Person {id:$a})-[:WROTE]->(d:Doc)<-[:WROTE]-(b:Person {id:$b})
RETURN DISTINCT d.id, d.title, d.path
LIMIT 5
