"""Small rustworkx matching wrapper."""

from __future__ import annotations

from collections.abc import Iterable

import rustworkx as rx


def compute_maximum_weight_matching_total(
    *,
    node_count: int,
    weighted_edges: Iterable[tuple[int, int, int]],
    max_cardinality: bool = True,
) -> tuple[int, int]:
    """Return matching cardinality and total weight for an indexed graph.

    Notes:
    - This wrapper keeps graph-index handling isolated from pairing logic.
    - Edge weights are expected to be safe C/Rust integers for rustworkx.
    """
    graph = rx.PyGraph()
    graph.add_nodes_from([None] * node_count)
    graph.extend_from_weighted_edge_list(weighted_edges)

    matched = rx.max_weight_matching(
        graph,
        max_cardinality=max_cardinality,
        weight_fn=int,
        default_weight=1,
    )

    total_weight = sum(
        int(graph.get_edge_data(left_index, right_index))
        for left_index, right_index in matched
    )
    return (len(matched), total_weight)
