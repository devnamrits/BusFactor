// PRs both people touched — authored or reviewed.
MATCH (a:Person {id:$a})-[:AUTHORED|REVIEWED]->(pr:PR)<-[:AUTHORED|REVIEWED]-(b:Person {id:$b})
RETURN DISTINCT pr.number, pr.title, pr.merged_at
ORDER BY pr.merged_at DESC
LIMIT 5
