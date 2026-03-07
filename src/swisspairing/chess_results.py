"""Helpers for reconstructing Swiss snapshots from Chess-Results XLSX exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree
from zipfile import ZipFile

if TYPE_CHECKING:
    from collections.abc import Sequence

_XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_HALF_POINT_GLYPH = "\u00bd"
_DRAW_RESULT_TEXT = f"{_HALF_POINT_GLYPH} - {_HALF_POINT_GLYPH}"


@dataclass(frozen=True, slots=True)
class ChessResultsPlayerRecord:
    starting_number: int
    title: str
    name: str
    fide_id: str
    federation: str
    rating: int
    sex: str


@dataclass(frozen=True, slots=True)
class ChessResultsPairingRecord:
    round_number: int
    board_number: int
    white_starting_number: int
    white_name: str
    white_rating: int
    white_points_times_ten: int
    result_text: str
    black_points_times_ten: int | None
    black_name: str | None
    black_rating: int | None
    black_starting_number: int | None
    seat_kind: str


@dataclass(frozen=True, slots=True)
class ChessResultsRoundRecord:
    round_number: int
    label: str
    pairings: tuple[ChessResultsPairingRecord, ...]


@dataclass(frozen=True, slots=True)
class ChessResultsTournamentRecord:
    name: str
    last_update: str
    players: tuple[ChessResultsPlayerRecord, ...]
    rounds: tuple[ChessResultsRoundRecord, ...]
    first_round_color_white1: bool


@dataclass(frozen=True, slots=True)
class ChessResultsRoundToken:
    opponent_starting_number: int
    color: str
    result: str


@dataclass(frozen=True, slots=True)
class ChessResultsPlayerSnapshot:
    player: ChessResultsPlayerRecord
    points_times_ten: int
    rank: int
    results: tuple[ChessResultsRoundToken, ...]


@dataclass(frozen=True, slots=True)
class ChessResultsSnapshot:
    tournament_name: str
    target_round_number: int
    total_rounds: int
    first_round_color_white1: bool
    players: tuple[ChessResultsPlayerSnapshot, ...]


def load_chess_results_rows(path: Path) -> tuple[tuple[str, ...], ...]:
    """Load the first worksheet of a simple XLSX workbook into row tuples."""
    with ZipFile(path) as workbook:
        shared_strings = _load_shared_strings(workbook)
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml")
    root = ElementTree.fromstring(sheet_xml)

    rows: list[tuple[str, ...]] = []
    for row in root.findall(".//a:sheetData/a:row", _XLSX_NS):
        values_by_column: dict[int, str] = {}
        for cell in row.findall("a:c", _XLSX_NS):
            reference = cell.get("r")
            if reference is None:
                continue
            column_name = "".join(character for character in reference if character.isalpha())
            if not column_name:
                continue
            values_by_column[_column_number(column_name)] = _cell_value(
                cell,
                shared_strings=shared_strings,
            )
        if not values_by_column:
            continue
        max_column = max(values_by_column)
        rows.append(tuple(values_by_column.get(index, "") for index in range(1, max_column + 1)))
    return tuple(rows)


def parse_chess_results_points(text: str) -> int:
    """Parse Chess-Results point text into tenths."""
    stripped = text.strip()
    if not stripped:
        return 0
    normalized = stripped.replace(_HALF_POINT_GLYPH, ".5")
    return int(round(float(normalized) * 10))


def parse_chess_results_starting_list(
    rows: Sequence[Sequence[str]],
) -> tuple[ChessResultsPlayerRecord, ...]:
    """Parse a Chess-Results starting-list export."""
    parsed: list[ChessResultsPlayerRecord] = []
    for row in rows:
        if not row or not row[0].strip().isdigit():
            continue
        parsed.append(
            ChessResultsPlayerRecord(
                starting_number=int(row[0].strip()),
                title=row[2].strip() if len(row) > 2 else "",
                name=row[3].strip() if len(row) > 3 else "",
                fide_id=row[4].strip() if len(row) > 4 else "",
                federation=row[5].strip() if len(row) > 5 else "",
                rating=int(row[6].strip() or 0) if len(row) > 6 else 0,
                sex=row[7].strip() if len(row) > 7 else "",
            )
        )
    return tuple(parsed)


def parse_chess_results_round(
    rows: Sequence[Sequence[str]],
) -> ChessResultsRoundRecord:
    """Parse one Chess-Results pairings/results export."""
    label = next(
        (
            row[0].strip()
            for row in rows
            if row
            and row[0].strip().lower().startswith("round ")
            and " on " in row[0].lower()
        ),
        "",
    )
    if not label:
        raise ValueError("round label not found in Chess-Results export")
    round_number = _parse_round_number(label)

    parsed: list[ChessResultsPairingRecord] = []
    for row in rows:
        if not row or not row[0].strip().isdigit():
            continue
        black_name = row[10].strip() if len(row) > 10 else ""
        seat_kind = _seat_kind(black_name)
        black_starting_number = (
            int(row[13].strip())
            if len(row) > 13 and row[13].strip().isdigit()
            else None
        )
        parsed.append(
            ChessResultsPairingRecord(
                round_number=round_number,
                board_number=int(row[0].strip()),
                white_starting_number=int(row[1].strip()),
                white_name=row[4].strip() if len(row) > 4 else "",
                white_rating=int(row[5].strip() or 0) if len(row) > 5 else 0,
                white_points_times_ten=parse_chess_results_points(row[6] if len(row) > 6 else ""),
                result_text=_normalize_result_text(row[7] if len(row) > 7 else ""),
                black_points_times_ten=(
                    parse_chess_results_points(row[8]) if len(row) > 8 and row[8].strip() else None
                ),
                black_name=black_name or None,
                black_rating=(
                    int(row[11].strip() or 0) if len(row) > 11 and row[11].strip() else None
                ),
                black_starting_number=black_starting_number,
                seat_kind=seat_kind,
            )
        )
    return ChessResultsRoundRecord(
        round_number=round_number,
        label=label,
        pairings=tuple(parsed),
    )


def load_chess_results_tournament(
    *,
    starting_list_path: Path,
    round_paths: Sequence[Path],
) -> ChessResultsTournamentRecord:
    starting_rows = load_chess_results_rows(starting_list_path)
    players = parse_chess_results_starting_list(starting_rows)
    rounds = tuple(parse_chess_results_round(load_chess_results_rows(path)) for path in round_paths)
    if not rounds:
        raise ValueError("at least one round export is required")

    name = next((row[0].strip() for row in starting_rows if row and row[0].strip()), "")
    if len(starting_rows) > 1 and starting_rows[1] and starting_rows[1][0].strip():
        name = starting_rows[1][0].strip()
    last_update = next(
        (
            row[0].strip()
            for row in starting_rows
            if row and row[0].strip().lower().startswith("last update ")
        ),
        "",
    )
    first_round_color_white1 = _infer_first_round_color_white1(rounds[0])
    return ChessResultsTournamentRecord(
        name=name,
        last_update=last_update,
        players=players,
        rounds=rounds,
        first_round_color_white1=first_round_color_white1,
    )


def build_chess_results_snapshot(
    tournament: ChessResultsTournamentRecord,
    *,
    target_round_number: int,
) -> ChessResultsSnapshot:
    """Build a pre-round snapshot from parsed Chess-Results exports."""
    if target_round_number < 1 or target_round_number > len(tournament.rounds):
        raise ValueError("target_round_number out of range")

    results_by_player: dict[int, list[ChessResultsRoundToken]] = {
        player.starting_number: [] for player in tournament.players
    }
    completed_rounds = target_round_number - 1

    for round_record in tournament.rounds[:completed_rounds]:
        seen_players: set[int] = set()
        for pairing in round_record.pairings:
            seen_players.add(pairing.white_starting_number)
            if pairing.seat_kind == "game":
                if pairing.black_starting_number is None:
                    raise ValueError("game row missing black starting number")
                seen_players.add(pairing.black_starting_number)
                white_token, black_token = _game_result_tokens(pairing.result_text)
                results_by_player[pairing.white_starting_number].append(
                    ChessResultsRoundToken(
                        opponent_starting_number=pairing.black_starting_number,
                        color="w",
                        result=white_token,
                    )
                )
                results_by_player[pairing.black_starting_number].append(
                    ChessResultsRoundToken(
                        opponent_starting_number=pairing.white_starting_number,
                        color="b",
                        result=black_token,
                    )
                )
                continue

            results_by_player[pairing.white_starting_number].append(
                ChessResultsRoundToken(
                    opponent_starting_number=0,
                    color="-",
                    result=_non_game_result_token(
                        result_text=pairing.result_text,
                        seat_kind=pairing.seat_kind,
                    ),
                )
            )

        for player in tournament.players:
            if player.starting_number in seen_players:
                continue
            # Some Chess-Results exports omit withdrawn players entirely.
            results_by_player[player.starting_number].append(
                ChessResultsRoundToken(
                    opponent_starting_number=0,
                    color="-",
                    result="Z",
                )
            )

    current_points = {
        player.starting_number: sum(
            _token_points_times_ten(token.result)
            for token in results_by_player[player.starting_number]
        )
        for player in tournament.players
    }

    _validate_pre_round_points(
        tournament=tournament,
        target_round_number=target_round_number,
        current_points=current_points,
    )

    ranking = sorted(
        tournament.players,
        key=lambda player: (
            -current_points[player.starting_number],
            -player.rating,
            player.starting_number,
        ),
    )
    rank_by_number = {
        player.starting_number: index for index, player in enumerate(ranking, start=1)
    }

    snapshots = tuple(
        ChessResultsPlayerSnapshot(
            player=player,
            points_times_ten=current_points[player.starting_number],
            rank=rank_by_number[player.starting_number],
            results=tuple(results_by_player[player.starting_number]),
        )
        for player in sorted(tournament.players, key=lambda player: player.starting_number)
    )
    return ChessResultsSnapshot(
        tournament_name=tournament.name,
        target_round_number=target_round_number,
        total_rounds=len(tournament.rounds),
        first_round_color_white1=tournament.first_round_color_white1,
        players=snapshots,
    )


def published_pairings_for_round(
    round_record: ChessResultsRoundRecord,
) -> tuple[tuple[str, str | None], ...]:
    normalized: list[tuple[str, str | None]] = []
    for pairing in round_record.pairings:
        white_id = str(pairing.white_starting_number)
        if pairing.seat_kind != "game" or pairing.black_starting_number is None:
            normalized.append((white_id, None))
            continue
        left, right = sorted((white_id, str(pairing.black_starting_number)))
        normalized.append((left, right))
    normalized.sort(key=lambda pair: (pair[1] is None, pair[0], pair[1] or ""))
    return tuple(normalized)


def _load_shared_strings(workbook: ZipFile) -> tuple[str, ...]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return ()
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", _XLSX_NS):
        fragments = [node.text or "" for node in item.findall(".//a:t", _XLSX_NS)]
        values.append("".join(fragments))
    return tuple(values)


def _column_number(column_name: str) -> int:
    value = 0
    for character in column_name:
        value = (value * 26) + (ord(character) - 64)
    return value


def _cell_value(
    cell: ElementTree.Element,
    *,
    shared_strings: Sequence[str],
) -> str:
    value_node = cell.find("a:v", _XLSX_NS)
    if value_node is None:
        return ""
    raw_value = value_node.text or ""
    if cell.get("t") == "s":
        return shared_strings[int(raw_value)]
    return raw_value


def _parse_round_number(label: str) -> int:
    prefix = "round "
    lowered = label.lower()
    if not lowered.startswith(prefix):
        raise ValueError(f"cannot parse round label {label!r}")
    number_text = label[len(prefix) :].split(" ", 1)[0]
    return int(number_text)


def _seat_kind(black_name: str) -> str:
    lowered = black_name.strip().lower()
    if lowered == "bye":
        return "bye"
    if lowered == "not paired":
        return "not_paired"
    return "game"


def _normalize_result_text(text: str) -> str:
    return " ".join(text.strip().split())


def _infer_first_round_color_white1(round_record: ChessResultsRoundRecord) -> bool:
    for pairing in round_record.pairings:
        if pairing.white_starting_number == 1:
            return True
        if pairing.black_starting_number == 1:
            return False
    raise ValueError("starting number 1 not found in first-round export")


def _game_result_tokens(result_text: str) -> tuple[str, str]:
    if result_text == "1 - 0":
        return ("1", "0")
    if result_text == "0 - 1":
        return ("0", "1")
    if result_text == _DRAW_RESULT_TEXT:
        return ("=", "=")
    if result_text == "+ - -":
        return ("+", "-")
    if result_text == "- - +":
        return ("-", "+")
    raise ValueError(f"unsupported Chess-Results game result {result_text!r}")


def _non_game_result_token(*, result_text: str, seat_kind: str) -> str:
    points_times_ten = parse_chess_results_points(result_text)
    if points_times_ten == 10:
        return "U" if seat_kind == "bye" else "F"
    if points_times_ten == 5:
        return "H"
    if points_times_ten == 0:
        return "Z"
    raise ValueError(
        f"unsupported Chess-Results non-game result {result_text!r} for {seat_kind!r}"
    )


def _token_points_times_ten(result_token: str) -> int:
    if result_token in {"1", "+", "W", "F", "U"}:
        return 10
    if result_token in {"=", "D", "H"}:
        return 5
    return 0


def _validate_pre_round_points(
    *,
    tournament: ChessResultsTournamentRecord,
    target_round_number: int,
    current_points: dict[int, int],
) -> None:
    round_record = tournament.rounds[target_round_number - 1]
    for pairing in round_record.pairings:
        expected_white = pairing.white_points_times_ten
        actual_white = current_points[pairing.white_starting_number]
        if actual_white != expected_white:
            raise ValueError(
                "white pre-round points mismatch for round "
                f"{target_round_number}, player {pairing.white_starting_number}: "
                f"{actual_white} != {expected_white}"
            )
        if pairing.black_starting_number is None or pairing.black_points_times_ten is None:
            continue
        actual_black = current_points[pairing.black_starting_number]
        expected_black = pairing.black_points_times_ten
        if actual_black != expected_black:
            raise ValueError(
                "black pre-round points mismatch for round "
                f"{target_round_number}, player {pairing.black_starting_number}: "
                f"{actual_black} != {expected_black}"
            )
