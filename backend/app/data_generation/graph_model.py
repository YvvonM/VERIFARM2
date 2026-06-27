"""
Minimal in-memory graph representation for the fake dataset.

Deliberately NOT a heavy graph library (e.g. networkx) -- per the "clean
Pythonic patterns over heavy abstractions" principle this project has
followed throughout. A node is a label + dict of properties; a relationship
is a (start_id, rel_type, end_id, properties) tuple. This is enough to:
  - validate against schemas/graph_schema.py before anything touches Neo4j
  - serialize to Cypher (cypher_export.py)
  - load directly via the neo4j driver (neo4j_loader.py)
without needing a third-party graph data structure for what's fundamentally
a flat list of records.
"""

from dataclasses import dataclass, field


def institution_id_for_org(org_id: str) -> str:
    """The reified Institution mirror of a registry Organization gets its own
    id (never the same id as the Organization node) -- two distinct nodes for
    one real-world actor, kept addressable by label."""
    return f"inst_{org_id}"


@dataclass
class GraphNode:
    label: str
    properties: dict


@dataclass
class GraphRelationship:
    start_label: str
    start_id: str
    rel_type: str
    end_label: str
    end_id: str
    properties: dict = field(default_factory=dict)


@dataclass
class FakeDataset:
    """
    The full generated dataset: every node and relationship, kept as flat
    lists rather than nested objects, so exporting to Cypher or loading via
    the driver is a simple iteration with no tree-walking required.
    """
    nodes: list[GraphNode] = field(default_factory=list)
    relationships: list[GraphRelationship] = field(default_factory=list)

    def add_node(self, label: str, properties: dict) -> None:
        self.nodes.append(GraphNode(label=label, properties=properties))

    def add_relationship(
        self,
        start_label: str,
        start_id: str,
        rel_type: str,
        end_label: str,
        end_id: str,
        properties: dict | None = None,
    ) -> None:
        self.relationships.append(
            GraphRelationship(
                start_label=start_label,
                start_id=start_id,
                rel_type=rel_type,
                end_label=end_label,
                end_id=end_id,
                properties=properties or {},
            )
        )

    def summary(self) -> str:
        node_counts: dict[str, int] = {}
        for n in self.nodes:
            node_counts[n.label] = node_counts.get(n.label, 0) + 1

        rel_counts: dict[str, int] = {}
        for r in self.relationships:
            rel_counts[r.rel_type] = rel_counts.get(r.rel_type, 0) + 1

        lines = ["Nodes:"]
        for label, count in sorted(node_counts.items()):
            lines.append(f"  {label}: {count}")
        lines.append("Relationships:")
        for rel_type, count in sorted(rel_counts.items()):
            lines.append(f"  {rel_type}: {count}")
        return "\n".join(lines)