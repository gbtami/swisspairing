"""Small rustworkx matching wrappers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import rustworkx as rx


def compute_maximum_weight_matching(
    *,
    node_ids: tuple[str, ...],
    edge_weights: dict[tuple[str, str], int],
    max_cardinality: bool = True,
) -> set[tuple[str, str]]:
    """Return a normalized maximum-weight matching over external node ids."""
    index_by_node = {node_id: index for index, node_id in enumerate(node_ids)}
    graph = rx.PyGraph()
    graph.add_nodes_from(node_ids)
    graph.extend_from_weighted_edge_list(
        (
            index_by_node[left_id],
            index_by_node[right_id],
            weight,
        )
        for (left_id, right_id), weight in edge_weights.items()
    )

    matched = rx.max_weight_matching(
        graph,
        max_cardinality=max_cardinality,
        weight_fn=int,
        default_weight=1,
    )
    return {
        cast(
            tuple[str, str],
            tuple(sorted((node_ids[left_index], node_ids[right_index]))),
        )
        for left_index, right_index in matched
    }


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
        int(graph.get_edge_data(left_index, right_index)) for left_index, right_index in matched
    )
    return (len(matched), total_weight)
