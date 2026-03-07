"""Unit tests for rustworkx matching wrapper."""

from swisspairing._matching import compute_maximum_weight_matching


def test_matching_empty_graph_returns_empty_set() -> None:
    matching = compute_maximum_weight_matching(node_ids=(), edge_weights={})
    assert matching == set()


def test_matching_selects_heaviest_edge_for_single_pair_case() -> None:
    matching = compute_maximum_weight_matching(
        node_ids=("a", "b", "c"),
        edge_weights={
            ("a", "b"): 10,
            ("a", "c"): 5,
            ("b", "c"): 1,
        },
    )
    assert matching == {("a", "b")}


def test_matching_normalizes_result_node_order() -> None:
    matching = compute_maximum_weight_matching(
        node_ids=("a", "b"),
        edge_weights={("b", "a"): 7},
    )
    assert matching == {("a", "b")}


def test_matching_uses_disjoint_edges_when_possible() -> None:
    matching = compute_maximum_weight_matching(
        node_ids=("a", "b", "c", "d"),
        edge_weights={
            ("a", "b"): 10,
            ("c", "d"): 8,
            ("a", "c"): 1,
            ("b", "d"): 1,
        },
    )
    assert matching == {("a", "b"), ("c", "d")}
