"""Helpers for importing complete Chess-Results event exports."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Sequence


_DEFAULT_QUERY = {
    "lan": "1",
    "turdet": "YES",
    "flag": "30",
}


@dataclass(frozen=True, slots=True)
class ChessResultsPageLink:
    text: str
    url: str


@dataclass(frozen=True, slots=True)
class ChessResultsEventPage:
    event_url: str
    tournament_name: str
    tournament_type: str
    declared_round_count: int
    round_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ChessResultsDownloadTarget:
    filename: str
    url: str
    round_number: int | None = None


@dataclass(frozen=True, slots=True)
class ChessResultsImportPlan:
    event_url: str
    tournament_name: str
    tournament_type: str
    declared_round_count: int
    round_numbers: tuple[int, ...]
    starting_list: ChessResultsDownloadTarget
    round_exports: tuple[ChessResultsDownloadTarget, ...]


@dataclass(frozen=True, slots=True)
class ChessResultsDownloadedEvent:
    starting_list_path: Path
    round_paths: tuple[Path, ...]


def canonicalize_chess_results_event_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError("expected a full Chess-Results event URL")
    if "chess-results" not in parts.netloc.lower():
        raise ValueError("expected a Chess-Results event URL")

    path = parts.path.replace(" ", "")
    if not path.lower().startswith("/tnr") or not path.lower().endswith(".aspx"):
        raise ValueError("unsupported Chess-Results event URL")

    return _with_query(
        urlunsplit((parts.scheme, parts.netloc, path, "", "")),
        _DEFAULT_QUERY,
    )


def fetch_chess_results_page_html(
    event_url: str,
    *,
    timeout_seconds: float = 30.0,
) -> str:
    canonical_url = canonicalize_chess_results_event_url(event_url)
    request = Request(canonical_url, headers={"User-Agent": "swisspairing/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def parse_chess_results_event_page(
    html: str,
    *,
    event_url: str,
) -> ChessResultsEventPage:
    parser = _ChessResultsEventHtmlParser(base_url=event_url)
    parser.feed(html)

    tournament_name = parser.heading or _fallback_tournament_name(parser.rows)
    if not tournament_name:
        raise ValueError("could not determine tournament name from Chess-Results page")

    metadata = _metadata_from_rows(parser.rows)
    round_count_text = metadata.get("number of rounds")
    if round_count_text is None or not round_count_text.isdigit():
        raise ValueError("could not determine round count from Chess-Results page")

    tournament_type = metadata.get("tournament type", "")
    round_numbers = _extract_round_numbers(parser.links)

    return ChessResultsEventPage(
        event_url=event_url,
        tournament_name=tournament_name,
        tournament_type=tournament_type,
        declared_round_count=int(round_count_text),
        round_numbers=round_numbers,
    )


def build_chess_results_import_plan(page: ChessResultsEventPage) -> ChessResultsImportPlan:
    if "swiss" not in page.tournament_type.lower():
        raise ValueError(
            "unsupported Chess-Results tournament type "
            f"{page.tournament_type!r}; only Swiss events are supported"
        )
    if not page.round_numbers:
        raise ValueError("Board Pairings links not found on Chess-Results event page")
    if page.round_numbers != tuple(range(1, page.round_numbers[-1] + 1)):
        raise ValueError(
            f"Chess-Results round links are not contiguous from round 1: {page.round_numbers!r}"
        )
    if page.round_numbers[-1] > page.declared_round_count:
        raise ValueError(
            "Chess-Results round links exceed the declared round count: "
            f"{page.round_numbers[-1]} > {page.declared_round_count}"
        )

    starting_list = ChessResultsDownloadTarget(
        filename="chessResultsList.xlsx",
        url=_with_query(
            page.event_url,
            {
                "zeilen": "99999",
                "prt": "4",
                "excel": "2010",
            },
        ),
    )
    round_exports = tuple(
        ChessResultsDownloadTarget(
            filename=f"chessResultsList({round_number}).xlsx",
            round_number=round_number,
            url=_with_query(
                page.event_url,
                {
                    "art": "2",
                    "rd": str(round_number),
                    "zeilen": "99999",
                    "prt": "4",
                    "excel": "2010",
                },
            ),
        )
        for round_number in page.round_numbers
    )
    return ChessResultsImportPlan(
        event_url=page.event_url,
        tournament_name=page.tournament_name,
        tournament_type=page.tournament_type,
        declared_round_count=page.declared_round_count,
        round_numbers=page.round_numbers,
        starting_list=starting_list,
        round_exports=round_exports,
    )


def load_chess_results_import_plan(
    event_url: str,
    *,
    timeout_seconds: float = 30.0,
) -> ChessResultsImportPlan:
    canonical_url = canonicalize_chess_results_event_url(event_url)
    html = fetch_chess_results_page_html(canonical_url, timeout_seconds=timeout_seconds)
    page = parse_chess_results_event_page(html, event_url=canonical_url)
    return build_chess_results_import_plan(page)


def download_chess_results_import_plan(
    plan: ChessResultsImportPlan,
    *,
    download_dir: Path,
    timeout_seconds: float = 60.0,
) -> ChessResultsDownloadedEvent:
    download_dir.mkdir(parents=True, exist_ok=True)

    starting_list_path = download_dir / plan.starting_list.filename
    _download_to_path(plan.starting_list.url, starting_list_path, timeout_seconds=timeout_seconds)

    round_paths: list[Path] = []
    for target in plan.round_exports:
        path = download_dir / target.filename
        _download_to_path(target.url, path, timeout_seconds=timeout_seconds)
        round_paths.append(path)

    return ChessResultsDownloadedEvent(
        starting_list_path=starting_list_path,
        round_paths=tuple(round_paths),
    )


def _download_to_path(url: str, path: Path, *, timeout_seconds: float) -> None:
    request = Request(url, headers={"User-Agent": "swisspairing/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
    path.write_bytes(payload)


def _with_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            "",
        )
    )


def _fallback_tournament_name(rows: Sequence[Sequence[str]]) -> str:
    single_cell_rows = [row[0].strip() for row in rows if len(row) == 1 and row[0].strip()]
    for index, text in enumerate(single_cell_rows):
        if "from the tournament-database" in text.lower() and index + 1 < len(single_cell_rows):
            return single_cell_rows[index + 1]
    return single_cell_rows[0] if single_cell_rows else ""


def _metadata_from_rows(rows: Sequence[Sequence[str]]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in rows:
        if len(row) < 2:
            continue
        label = _normalize_space(row[0]).rstrip(":").lower()
        value = _normalize_space(row[1])
        if label and value and label not in metadata:
            metadata[label] = value
    return metadata


def _extract_round_numbers(links: Sequence[ChessResultsPageLink]) -> tuple[int, ...]:
    round_numbers = {
        int(query["rd"])
        for link in links
        if (query := dict(parse_qsl(urlsplit(link.url).query))).get("art") == "2"
        and query.get("rd", "").isdigit()
    }
    return tuple(sorted(round_numbers))


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


class _ChessResultsEventHtmlParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self.rows: list[tuple[str, ...]] = []
        self.links: list[ChessResultsPageLink] = []
        self.heading = ""

        self._current_row: list[str] | None = None
        self._current_cell_fragments: list[str] | None = None
        self._current_heading_fragments: list[str] | None = None
        self._current_link_href: str | None = None
        self._current_link_fragments: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._current_row = []
            return
        if tag in {"td", "th"} and self._current_row is not None:
            self._current_cell_fragments = []
            return
        if tag == "h2":
            self._current_heading_fragments = []
            return
        if tag == "a":
            href = attributes.get("href")
            if href is None:
                return
            self._current_link_href = urljoin(self._base_url, href)
            self._current_link_fragments = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell_fragments is not None:
            if self._current_row is not None:
                self._current_row.append(_normalize_space("".join(self._current_cell_fragments)))
            self._current_cell_fragments = None
            return
        if tag == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self.rows.append(tuple(self._current_row))
            self._current_row = None
            return
        if tag == "h2" and self._current_heading_fragments is not None:
            heading = _normalize_space("".join(self._current_heading_fragments))
            if heading and not self.heading:
                self.heading = heading
            self._current_heading_fragments = None
            return
        if (
            tag == "a"
            and self._current_link_href is not None
            and self._current_link_fragments is not None
        ):
            text = _normalize_space("".join(self._current_link_fragments))
            self.links.append(ChessResultsPageLink(text=text, url=self._current_link_href))
            self._current_link_href = None
            self._current_link_fragments = None

    def handle_data(self, data: str) -> None:
        if self._current_cell_fragments is not None:
            self._current_cell_fragments.append(data)
        if self._current_heading_fragments is not None:
            self._current_heading_fragments.append(data)
        if self._current_link_fragments is not None:
            self._current_link_fragments.append(data)
