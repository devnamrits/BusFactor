// Everything one person currently carries, heaviest first.
MATCH (p:Person {id:$person})-[k:KNOWS]->(m:Module)
RETURN m.id, m.name, k.weight, k.commits, m.commits_window
ORDER BY k.weight DESC, m.id
