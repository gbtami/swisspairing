from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

import pytest

from swisspairing.chess_results_site import (
    ChessResultsEventPage,
    build_chess_results_import_plan,
    canonicalize_chess_results_event_url,
    parse_chess_results_event_page,
)


def _query(url: str) -> dict[str, str]:
    return dict(parse_qsl(urlsplit(url).query))


def test_canonicalize_chess_results_event_url_strips_round_query() -> None:
    canonical = canonicalize_chess_results_event_url(
        "https://s1.chess-results.com/tnr1307079.aspx?lan=3&art=2&rd=4&turdet=NO"
    )

    assert canonical == "https://s1.chess-results.com/tnr1307079.aspx?lan=1&turdet=YES&flag=30"


def test_parse_chess_results_event_page_extracts_heading_metadata_and_rounds() -> None:
    html = """
    <html><body>
      <h2>Sample Swiss Event</h2>
      <table>
        <tr><td>Number of rounds</td><td>9</td></tr>
        <tr><td>Tournament type</td><td>Swiss-System</td></tr>
        <tr>
          <td>Board Pairings</td>
          <td>
            <a href="/tnr123.aspx?lan=1&amp;art=2&amp;rd=1&amp;turdet=YES&amp;flag=30">Rd.1</a>
            <a href="https://chess-results.com/tnr123.aspx?lan=1&amp;art=1&amp;rd=1">Rank</a>
            <a href="/tnr123.aspx?lan=1&amp;art=2&amp;rd=2&amp;turdet=YES&amp;flag=30">Rd.2</a>
            <a href="/tnr123.aspx?lan=1&amp;art=2&amp;rd=3&amp;turdet=YES&amp;flag=30">Rd.3</a>
          </td>
        </tr>
      </table>
    </body></html>
    """

    page = parse_chess_results_event_page(
        html,
        event_url="https://s1.chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
    )

    assert page == ChessResultsEventPage(
        event_url="https://s1.chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
        tournament_name="Sample Swiss Event",
        tournament_type="Swiss-System",
        declared_round_count=9,
        round_numbers=(1, 2, 3),
    )


def test_parse_chess_results_event_page_falls_back_to_single_cell_name() -> None:
    html = """
    <html><body>
      <table>
        <tr><td>From the Tournament-Database of Chess-Results</td></tr>
        <tr><td>Fallback Event Name</td></tr>
        <tr><td>Number of rounds</td><td>5</td></tr>
        <tr><td>Tournament type</td><td>Swiss-System</td></tr>
        <tr>
          <td>Board Pairings</td>
          <td>
            <a href="/tnr123.aspx?lan=1&amp;art=2&amp;rd=1&amp;turdet=YES&amp;flag=30">Rd.1</a>
          </td>
        </tr>
      </table>
    </body></html>
    """

    page = parse_chess_results_event_page(
        html,
        event_url="https://chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
    )

    assert page.tournament_name == "Fallback Event Name"


def test_build_chess_results_import_plan_builds_complete_download_urls() -> None:
    plan = build_chess_results_import_plan(
        ChessResultsEventPage(
            event_url="https://chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
            tournament_name="Sample Swiss Event",
            tournament_type="Swiss-System",
            declared_round_count=9,
            round_numbers=(1, 2, 3),
        )
    )

    assert plan.starting_list.filename == "chessResultsList.xlsx"
    assert _query(plan.starting_list.url) == {
        "lan": "1",
        "turdet": "YES",
        "flag": "30",
        "zeilen": "99999",
        "prt": "4",
        "excel": "2010",
    }
    assert [target.filename for target in plan.round_exports] == [
        "chessResultsList(1).xlsx",
        "chessResultsList(2).xlsx",
        "chessResultsList(3).xlsx",
    ]
    assert [target.round_number for target in plan.round_exports] == [1, 2, 3]
    assert _query(plan.round_exports[1].url) == {
        "lan": "1",
        "turdet": "YES",
        "flag": "30",
        "art": "2",
        "rd": "2",
        "zeilen": "99999",
        "prt": "4",
        "excel": "2010",
    }


def test_build_chess_results_import_plan_rejects_non_swiss_event() -> None:
    with pytest.raises(ValueError, match="only Swiss events are supported"):
        build_chess_results_import_plan(
            ChessResultsEventPage(
                event_url="https://chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
                tournament_name="Sample RR Event",
                tournament_type="Round robin",
                declared_round_count=9,
                round_numbers=(1, 2, 3),
            )
        )


def test_build_chess_results_import_plan_rejects_non_contiguous_round_links() -> None:
    with pytest.raises(ValueError, match="not contiguous from round 1"):
        build_chess_results_import_plan(
            ChessResultsEventPage(
                event_url="https://chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
                tournament_name="Sample Swiss Event",
                tournament_type="Swiss-System",
                declared_round_count=9,
                round_numbers=(1, 3),
            )
        )
