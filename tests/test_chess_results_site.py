from __future__ import annotations

from email.message import Message
from typing import cast
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request

import pytest

from swisspairing.chess_results_site import (
    ChessResultsEventPage,
    build_chess_results_import_plan,
    canonicalize_chess_results_event_url,
    fetch_chess_results_page_html,
    load_chess_results_import_plan,
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


def test_fetch_chess_results_page_html_posts_show_tournament_details_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_html = """
    <html><body>
      <form method="post" action="./tnr123.aspx?lan=1&amp;turdet=YES&amp;flag=30" id="form1">
        <input type="hidden" name="__VIEWSTATE" value="/wEP" />
        <input type="hidden" name="__VIEWSTATEGENERATOR" value="ABC123" />
        <input type="hidden" name="__EVENTVALIDATION" value="/wEd" />
        <input
          type="submit"
          value="Show tournament details"
          id="cb_alleDetails"
          name="cb_alleDetails"
        />
      </form>
    </body></html>
    """
    detailed_html = """
    <html><body>
      <h2>Sample Swiss Event</h2>
      <table>
        <tr><td>Number of rounds</td><td>7</td></tr>
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
    calls: list[tuple[str, bytes | None]] = []

    class _Response:
        def __init__(self, html: str) -> None:
            self._payload = html.encode("utf-8")
            self.headers = Message()
            self.headers["Content-Type"] = "text/html; charset=utf-8"

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    def fake_urlopen(request: Request, timeout: float) -> _Response:
        assert timeout == 30.0
        full_url = request.full_url
        data = cast(bytes | None, request.data)
        calls.append((full_url, data))
        return _Response(initial_html if len(calls) == 1 else detailed_html)

    monkeypatch.setattr("swisspairing.chess_results_site.urlopen", fake_urlopen)

    html = fetch_chess_results_page_html(
        "https://s3.chess-results.com/tnr123.aspx?lan=1",
        timeout_seconds=30.0,
    )

    assert html == detailed_html
    assert [url for url, _ in calls] == [
        "https://s3.chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
        "https://s3.chess-results.com/tnr123.aspx?lan=1&turdet=YES&flag=30",
    ]
    assert calls[0][1] is None
    assert calls[1][1] is not None
    posted = calls[1][1].decode("utf-8")
    assert "cb_alleDetails=Show+tournament+details" in posted
    assert "__VIEWSTATE=%2FwEP" in posted
    assert "__EVENTVALIDATION=%2FwEd" in posted


def test_load_chess_results_import_plan_handles_show_tournament_details_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_html = """
    <html><body>
      <form method="post" action="./tnr123.aspx?lan=1&amp;turdet=YES&amp;flag=30" id="form1">
        <input type="hidden" name="__VIEWSTATE" value="/wEP" />
        <input
          type="submit"
          value="Show tournament details"
          id="cb_alleDetails"
          name="cb_alleDetails"
        />
      </form>
    </body></html>
    """
    detailed_html = """
    <html><body>
      <h2>Sample Swiss Event</h2>
      <table>
        <tr><td>Number of rounds</td><td>5</td></tr>
        <tr><td>Tournament type</td><td>Swiss-System</td></tr>
        <tr>
          <td>Board Pairings</td>
          <td>
            <a href="/tnr123.aspx?lan=1&amp;art=2&amp;rd=1&amp;turdet=YES&amp;flag=30">Rd.1</a>
            <a href="/tnr123.aspx?lan=1&amp;art=2&amp;rd=2&amp;turdet=YES&amp;flag=30">Rd.2</a>
          </td>
        </tr>
      </table>
    </body></html>
    """

    class _Response:
        def __init__(self, html: str) -> None:
            self._payload = html.encode("utf-8")
            self.headers = Message()
            self.headers["Content-Type"] = "text/html; charset=utf-8"

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    responses = iter((_Response(initial_html), _Response(detailed_html)))

    def fake_urlopen(_: Request, timeout: float) -> _Response:
        assert timeout == 30.0
        return next(responses)

    monkeypatch.setattr("swisspairing.chess_results_site.urlopen", fake_urlopen)

    plan = load_chess_results_import_plan("https://s3.chess-results.com/tnr123.aspx")

    assert plan.tournament_name == "Sample Swiss Event"
    assert plan.declared_round_count == 5
    assert plan.round_numbers == (1, 2)


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
