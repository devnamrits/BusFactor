// Biggest modules by commit volume — for overview answers.
MATCH (m:Module)
RETURN m.id, m.name, m.commits_window
ORDER BY m.commits_window DESC, m.name
LIMIT 8
