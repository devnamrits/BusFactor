// Stranded knowledge: components holding a module but no active person.
CALL algo.WCC({nodeLabels:['Person','Module','Doc'], relationshipTypes:['KNOWS','OWNS','DOCUMENTS']})
YIELD node, componentId
RETURN componentId, labels(node), node.status, coalesce(node.name, node.title, node.path)
