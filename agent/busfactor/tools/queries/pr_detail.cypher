// One merged PR: who authored it, which modules it touched.
MATCH (pr:PR {id:$pr})
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(pr)
OPTIONAL MATCH (pr)-[:TOUCHES]->(m:Module)
RETURN pr.number, pr.title, pr.merged_at,
       collect(DISTINCT a.name) AS authors, collect(DISTINCT m.name) AS modules
