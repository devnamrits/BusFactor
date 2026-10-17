// The module index — used for name resolution.
MATCH (m:Module) RETURN m.id, m.name, m.path ORDER BY m.name
