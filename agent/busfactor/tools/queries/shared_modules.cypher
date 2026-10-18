// Modules two people both carry — joint familiarity = min of the two weights.
MATCH (a:Person {id:$a})-[ka:KNOWS|OWNS]->(m:Module)<-[kb:KNOWS|OWNS]-(b:Person {id:$b})
RETURN m.id, m.name, ka.weight, kb.weight
ORDER BY m.name
