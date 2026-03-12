"""Small rustworkx matching wrapper."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import rustworkx as rx


def compute_maximum_weight_matching(
    *,
    node_ids: Iterable[str],
    edge_weights: Mapping[tuple[str, str], int],
    max_cardinality: bool = True,
) -> set[tuple[str, str]]:
    """Return matching edges as `(node_id_a, node_id_b)` tuples.

    Notes:
    - This wrapper keeps graph-index handling isolated from pairing logic.
    - Edge weights are expected to be safe C/Rust integers for rustworkx.
    """
    graph = rx.PyGraph()
    ids = tuple(node_ids)
    id_to_index = {node_id: index for index, node_id in enumerate(ids)}
    graph.add_nodes_from([None] * len(ids))
    graph.extend_from_weighted_edge_list(
        (id_to_index[left_id], id_to_index[right_id], weight)
        for (left_id, right_id), weight in edge_weights.items()
    )

    matched = rx.max_weight_matching(
        graph,
        max_cardinality=max_cardinality,
        weight_fn=int,
        default_weight=1,
    )

    normalized: set[tuple[str, str]] = set()
    for left_index, right_index in matched:
        left_id = ids[left_index]
        right_id = ids[right_index]
        if left_id <= right_id:
            normalized.add((left_id, right_id))
        else:
            normalized.add((right_id, left_id))
    return normalized
