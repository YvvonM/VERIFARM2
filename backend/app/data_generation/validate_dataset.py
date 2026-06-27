"""
Validates a generated FakeDataset against schemas/graph_schema.py before
it's exported to Cypher or loaded into Neo4j. This catches generator bugs
(a typo'd label, a relationship triple that doesn't exist in the schema)
at generation time rather than as a confusing Neo4j error later, or worse,
silently-wrong data sitting in the graph that the agent then queries
against as if it were real.
"""

from dataclasses import dataclass, field

from app.data_generation.graph_model import FakeDataset
from app.schemas.graph_schema import NODE_SCHEMA, RELATIONSHIP_SCHEMA


@dataclass
class DatasetValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_dataset(dataset: FakeDataset) -> DatasetValidationResult:
    errors: list[str] = []
    known_node_labels = set(NODE_SCHEMA.keys())
    known_rel_triples = set(RELATIONSHIP_SCHEMA)

    # Every node's label must exist in the schema, and every property name
    # it sets must be one the schema actually declares for that label.
    for node in dataset.nodes:
        if node.label not in known_node_labels:
            errors.append(f"Unknown node label: {node.label}")
            continue

        expected_props = set(NODE_SCHEMA[node.label].keys())
        actual_props = set(node.properties.keys())
        unexpected = actual_props - expected_props
        if unexpected:
            errors.append(
                f"Node {node.label} has properties not in schema: {sorted(unexpected)}"
            )

    # Build a quick lookup of node id -> label, to check relationship
    # endpoints actually point at nodes that were declared with a matching
    # label (catches e.g. accidentally linking a Claim to a node typed as
    # the wrong label).
    node_label_by_id: dict[str, str] = {}
    for node in dataset.nodes:
        node_id = node.properties.get("id")
        if node_id is not None:
            node_label_by_id[node_id] = node.label

    for rel in dataset.relationships:
        triple = (rel.start_label, rel.rel_type, rel.end_label)
        if triple not in known_rel_triples:
            errors.append(f"Unknown relationship triple: {triple}")

        start_actual_label = node_label_by_id.get(rel.start_id)
        if start_actual_label is not None and start_actual_label != rel.start_label:
            errors.append(
                f"Relationship {rel.rel_type}: start_id {rel.start_id} is labeled "
                f"{start_actual_label} in the node list, but relationship declares "
                f"start_label {rel.start_label}"
            )

        end_actual_label = node_label_by_id.get(rel.end_id)
        if end_actual_label is not None and end_actual_label != rel.end_label:
            errors.append(
                f"Relationship {rel.rel_type}: end_id {rel.end_id} is labeled "
                f"{end_actual_label} in the node list, but relationship declares "
                f"end_label {rel.end_label}"
            )

    return DatasetValidationResult(is_valid=len(errors) == 0, errors=errors)