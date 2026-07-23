#!/usr/bin/env python3

"""成績MarkdownのWDL/Ptnmlから、Ordo相当の相対Ratingを直接計算する。"""

import argparse
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple


RATING_SCALE = math.log(0.76 / 0.24) / 202.0
DEFAULT_BOOTSTRAP_SAMPLES = 10_000
DEFAULT_RANDOM_SEED = 20260723
PAIR_SCORES = (0.0, 0.5, 1.0, 1.5, 2.0)
DETAILS_SECTION_RE = re.compile(
    r"<summary><strong>(.+?)</strong></summary>"
)


class MarkdownResultError(ValueError):
    """成績Markdownを安全に計算できない場合のエラー。"""


@dataclass(frozen=True)
class MatchResult:
    subject: str
    opponent: str
    games: int
    wins: int
    losses: int
    draws: int
    ptnml: Optional[Tuple[int, int, int, int, int]]
    line_number: int


@dataclass(frozen=True)
class ResultTable:
    section: str
    condition: str
    subject: str
    matches: Tuple[MatchResult, ...]


@dataclass(frozen=True)
class ResultGroup:
    section: str
    condition: str
    tables: Tuple[ResultTable, ...]


@dataclass(frozen=True)
class PlayerRating:
    name: str
    rating: float
    lower: Optional[float]
    upper: Optional[float]
    games: int
    first_place_rate: Optional[float]


@dataclass(frozen=True)
class TableAnalysis:
    table: ResultGroup
    players: Tuple[PlayerRating, ...]
    bootstrap_samples: int
    warning: Optional[str]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_integer(value: str, *, line_number: int, field: str) -> int:
    normalized = value.replace(",", "").strip()
    if not normalized.isdigit():
        raise MarkdownResultError(
            f"{line_number}行目の{field}を整数として読めません: {value}"
        )
    return int(normalized)


def _parse_wld(value: str, *, line_number: int) -> Tuple[int, int, int]:
    match = re.fullmatch(
        r"\s*([\d,]+)\s*[–−-]\s*([\d,]+)\s*[–−-]\s*([\d,]+)\s*",
        value,
    )
    if match is None:
        raise MarkdownResultError(
            f"{line_number}行目の成績を勝–敗–引分として読めません: {value}"
        )
    return tuple(int(item.replace(",", "")) for item in match.groups())


def _parse_ptnml(
    value: str, *, line_number: int
) -> Optional[Tuple[int, int, int, int, int]]:
    if value.strip() in {"", "-", "—"}:
        return None

    match = re.fullmatch(
        r"\[\s*([\d,]+)\s*,\s*([\d,]+)\s*,\s*([\d,]+)\s*,\s*"
        r"([\d,]+)\s*,\s*([\d,]+)\s*\]",
        value,
    )
    if match is None:
        raise MarkdownResultError(
            f"{line_number}行目のPtnmlを[LL, LD, DD, DW, WW]として読めません: "
            f"{value}"
        )
    return tuple(int(item.replace(",", "")) for item in match.groups())


def _validate_match(result: MatchResult) -> None:
    if result.games <= 0:
        raise MarkdownResultError(
            f"{result.line_number}行目の対局数は正の整数である必要があります"
        )
    if result.games != result.wins + result.losses + result.draws:
        raise MarkdownResultError(
            f"{result.line_number}行目の対局数と勝–敗–引分が一致しません"
        )
    if result.ptnml is None:
        return

    if result.games != 2 * sum(result.ptnml):
        raise MarkdownResultError(
            f"{result.line_number}行目の対局数とPtnmlが一致しません"
        )

    ll, ld, dd, dw, ww = result.ptnml
    wdl_half_points = 2 * result.wins + result.draws
    ptnml_half_points = ld + 2 * dd + 3 * dw + 4 * ww
    if wdl_half_points != ptnml_half_points:
        raise MarkdownResultError(
            f"{result.line_number}行目の勝–敗–引分とPtnmlの得点が一致しません"
        )


def parse_result_tables(text: str) -> Tuple[ResultTable, ...]:
    """Markdownの基準AI表とA vs B表を読み取る。"""

    lines = text.splitlines()
    section = ""
    condition = ""
    tables = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            section = line[3:].strip()
            condition = ""
            index += 1
            continue
        details_section = DETAILS_SECTION_RE.fullmatch(line.strip())
        if details_section is not None:
            section = details_section.group(1).strip()
            condition = ""
            index += 1
            continue
        if line.startswith("### "):
            condition = line[4:].strip()
            index += 1
            continue

        if not line.lstrip().startswith("|"):
            index += 1
            continue

        headers = _cells(line)
        score_columns = [
            column for column, header in enumerate(headers) if "成績" in header
        ]
        ptnml_columns = [
            column for column, header in enumerate(headers)
            if header.startswith("Ptnml")
        ]
        opponent_table = "対戦相手" in headers
        pair_table = "A vs B" in headers
        if (
            not (opponent_table or pair_table)
            or "対局数" not in headers
            or len(ptnml_columns) != 1
            or len(score_columns) != 1
        ):
            index += 1
            continue
        if not section or not condition:
            raise MarkdownResultError(
                f"{index + 1}行目の成績表には##版と###対局条件の見出しが必要です"
            )

        score_column = score_columns[0]
        score_header = headers[score_column]
        normalized_score_header = score_header.replace("-", "–").replace("−", "–")
        if "勝–敗–引分" not in normalized_score_header:
            raise MarkdownResultError(
                f"{index + 1}行目の成績列は勝–敗–引分の順である必要があります: "
                f"{score_header}"
            )
        if opponent_table:
            subject = score_header.split("成績", 1)[0].strip()
            if not subject:
                raise MarkdownResultError(
                    f"{index + 1}行目の成績列から基準AI名を取得できません"
                )
            participant_column = headers.index("対戦相手")
        else:
            if not score_header.startswith("A目線成績"):
                raise MarkdownResultError(
                    f"{index + 1}行目のA vs B表はA目線成績である必要があります"
                )
            subject = ""
            participant_column = headers.index("A vs B")

        if index + 1 >= len(lines) or not lines[index + 1].lstrip().startswith("|"):
            raise MarkdownResultError(
                f"{index + 1}行目の表に区切り行がありません"
            )

        games_column = headers.index("対局数")
        ptnml_column = ptnml_columns[0]
        index += 2
        matches = []

        while index < len(lines) and lines[index].lstrip().startswith("|"):
            values = _cells(lines[index])
            line_number = index + 1
            if len(values) != len(headers):
                raise MarkdownResultError(
                    f"{line_number}行目の列数が表見出しと一致しません"
                )

            if opponent_table:
                row_subject = subject
                opponent = values[participant_column]
                if not opponent:
                    raise MarkdownResultError(
                        f"{line_number}行目の対戦相手が空です"
                    )
            else:
                pairing = re.fullmatch(
                    r"\s*(.+?)\s+vs\s+(.+?)\s*",
                    values[participant_column],
                    flags=re.IGNORECASE,
                )
                if pairing is None:
                    raise MarkdownResultError(
                        f"{line_number}行目をA vs Bとして読めません: "
                        f"{values[participant_column]}"
                    )
                row_subject, opponent = (
                    participant.strip() for participant in pairing.groups()
                )

            if opponent == row_subject:
                raise MarkdownResultError(
                    f"{line_number}行目は同じAI同士の自己対局です: {row_subject}"
                )

            wins, losses, draws = _parse_wld(
                values[score_column], line_number=line_number
            )
            result = MatchResult(
                subject=row_subject,
                opponent=opponent,
                games=_parse_integer(
                    values[games_column],
                    line_number=line_number,
                    field="対局数",
                ),
                wins=wins,
                losses=losses,
                draws=draws,
                ptnml=_parse_ptnml(
                    values[ptnml_column], line_number=line_number
                ),
                line_number=line_number,
            )
            _validate_match(result)
            matches.append(result)
            index += 1

        if not matches:
            raise MarkdownResultError(
                f"{index + 1}行目までの成績表に結果行がありません"
            )
        tables.append(
            ResultTable(
                section=section,
                condition=condition,
                subject=subject,
                matches=tuple(matches),
            )
        )

    if not tables:
        raise MarkdownResultError(
            "対戦相手、対局数、成績、Ptnmlを持つ成績表が見つかりません"
        )
    return tuple(tables)


def group_result_tables(tables: Sequence[ResultTable]) -> Tuple[ResultGroup, ...]:
    """同じ版・対局条件の複数表を一つの対戦グラフへまとめる。"""

    grouped = {}
    order = []
    for table in tables:
        key = (table.section, table.condition)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(table)
    return tuple(
        ResultGroup(section, condition, tuple(grouped[(section, condition)]))
        for section, condition in order
    )


def _observations(group: ResultGroup):
    return tuple(
        (match.subject, match)
        for table in group.tables
        for match in table.matches
    )


def _player_names(group: ResultGroup) -> Tuple[str, ...]:
    names = []
    for subject, match in _observations(group):
        for name in (subject, match.opponent):
            if name not in names:
                names.append(name)
    return tuple(names)


def _connected_components(
    player_count: int, indexed_matches: Sequence[Tuple[int, int, int, float]]
) -> Tuple[Tuple[int, ...], ...]:
    neighbours = [set() for _ in range(player_count)]
    for subject_index, opponent_index, _, _ in indexed_matches:
        neighbours[subject_index].add(opponent_index)
        neighbours[opponent_index].add(subject_index)

    unseen = set(range(player_count))
    components = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        stack = [start]
        component = []
        while stack:
            player = stack.pop()
            component.append(player)
            for neighbour in neighbours[player]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        components.append(tuple(sorted(component)))
    return tuple(components)


def _solve_linear(matrix: Sequence[Sequence[float]], vector: Sequence[float]):
    size = len(vector)
    coefficients = [list(row) for row in matrix]
    values = list(vector)

    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: abs(coefficients[row][column]),
        )
        if abs(coefficients[pivot][column]) < 1e-14:
            raise MarkdownResultError(
                "Rating計算の連立方程式を解けません"
            )
        if pivot != column:
            coefficients[column], coefficients[pivot] = (
                coefficients[pivot],
                coefficients[column],
            )
            values[column], values[pivot] = values[pivot], values[column]

        for row in range(column + 1, size):
            factor = coefficients[row][column] / coefficients[column][column]
            if factor == 0.0:
                continue
            for item in range(column, size):
                coefficients[row][item] -= (
                    factor * coefficients[column][item]
                )
            values[row] -= factor * values[column]

    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        remainder = values[row] - sum(
            coefficients[row][column] * solution[column]
            for column in range(row + 1, size)
        )
        solution[row] = remainder / coefficients[row][row]
    return solution


def _log_likelihood(
    ratings: Sequence[float],
    indexed_matches: Sequence[Tuple[int, int, int, float]],
) -> float:
    total = 0.0
    for subject_index, opponent_index, games, score in indexed_matches:
        value = RATING_SCALE * (
            ratings[subject_index] - ratings[opponent_index]
        )
        if value >= 0.0:
            log_probability = -math.log1p(math.exp(-value))
            log_opposite = -value - math.log1p(math.exp(-value))
        else:
            log_probability = value - math.log1p(math.exp(value))
            log_opposite = -math.log1p(math.exp(value))
        total += score * log_probability
        total += (games - score) * log_opposite
    return total


def _solve_ratings(
    group: ResultGroup,
    sampled_scores: Optional[Sequence[float]] = None,
) -> Tuple[Tuple[str, ...], Tuple[float, ...]]:
    names = _player_names(group)
    if len(names) < 2:
        raise MarkdownResultError(
            f"{group.section} / {group.condition}の参加AIが2種類未満です"
        )
    player_indices = {name: index for index, name in enumerate(names)}
    observations = _observations(group)
    indexed_matches = []
    for match_index, (subject, match) in enumerate(observations):
        score = (
            match.wins + match.draws / 2.0
            if sampled_scores is None
            else sampled_scores[match_index]
        )
        if not 0.0 < score < match.games:
            raise MarkdownResultError(
                "全勝または全敗の比較から有限のRating差を計算できません"
            )
        indexed_matches.append(
            (
                player_indices[subject],
                player_indices[match.opponent],
                match.games,
                score,
            )
        )

    components = _connected_components(len(names), indexed_matches)
    if len(components) != 1:
        labels = [
            ", ".join(names[player] for player in component)
            for component in components
        ]
        raise MarkdownResultError(
            f"{group.section} / {group.condition}の対戦グラフが連結していません: "
            + " / ".join(labels)
        )

    ratings = [0.0] * len(names)
    for _ in range(100):
        gradient = [0.0] * len(names)
        information = [
            [0.0] * len(names) for _ in range(len(names))
        ]
        for subject_index, opponent_index, games, score in indexed_matches:
            value = RATING_SCALE * (
                ratings[subject_index] - ratings[opponent_index]
            )
            probability = (
                1.0 / (1.0 + math.exp(-value))
                if value >= 0.0
                else math.exp(value) / (1.0 + math.exp(value))
            )
            error = RATING_SCALE * (score - games * probability)
            gradient[subject_index] += error
            gradient[opponent_index] -= error

            weight = (
                RATING_SCALE * RATING_SCALE * games
                * probability * (1.0 - probability)
            )
            information[subject_index][subject_index] += weight
            information[opponent_index][opponent_index] += weight
            information[subject_index][opponent_index] -= weight
            information[opponent_index][subject_index] -= weight

        reduced_information = [
            row[:-1] for row in information[:-1]
        ]
        reduced_step = _solve_linear(
            reduced_information, gradient[:-1]
        )
        step = reduced_step + [0.0]
        baseline = _log_likelihood(ratings, indexed_matches)
        step_scale = 1.0

        for _ in range(25):
            candidate = [
                rating + step_scale * change
                for rating, change in zip(ratings, step)
            ]
            average = sum(candidate) / len(candidate)
            candidate = [rating - average for rating in candidate]
            if (
                _log_likelihood(candidate, indexed_matches)
                >= baseline - 1e-10
            ):
                break
            step_scale /= 2.0
        else:
            raise MarkdownResultError(
                "Rating計算の尤度を改善できません"
            )

        change = max(
            abs(after - before)
            for before, after in zip(ratings, candidate)
        )
        ratings = candidate
        if (
            not all(math.isfinite(rating) for rating in ratings)
            or max(abs(rating) for rating in ratings) > 100_000
        ):
            raise MarkdownResultError(
                "有限のRatingを推定できません"
            )
        if change < 1e-9:
            return names, tuple(ratings)

    raise MarkdownResultError(
        "Rating計算が100回以内に収束しません"
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return (
        ordered[lower_index] * (1.0 - fraction)
        + ordered[upper_index] * fraction
    )


def _bootstrap(
    group: ResultGroup, samples: int, seed: int
) -> Tuple[Tuple[float, ...], ...]:
    generator = random.Random(seed)
    names = _player_names(group)
    observations = _observations(group)
    output = [[] for _ in names]
    completed = 0
    attempts = 0
    maximum_attempts = max(samples * 10, 100)

    while completed < samples and attempts < maximum_attempts:
        attempts += 1
        sampled_scores = []
        for _, match in observations:
            assert match.ptnml is not None
            pair_count = sum(match.ptnml)
            sampled_scores.append(
                sum(
                    generator.choices(
                        PAIR_SCORES,
                        weights=match.ptnml,
                        k=pair_count,
                    )
                )
            )

        try:
            sampled_names, ratings = _solve_ratings(group, sampled_scores)
        except MarkdownResultError:
            continue
        if sampled_names != names:
            raise MarkdownResultError(
                "bootstrap中に参加AIの順序が変化しました"
            )

        for player_index, rating in enumerate(ratings):
            output[player_index].append(rating)
        completed += 1

    if completed != samples:
        raise MarkdownResultError(
            "Ptnml bootstrapで有限のRating標本を必要数生成できません"
        )
    return tuple(tuple(values) for values in output)


def analyze_group(
    group: ResultGroup,
    *,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_RANDOM_SEED,
) -> TableAnalysis:
    if bootstrap_samples < 0:
        raise MarkdownResultError("bootstrap回数は0以上で指定してください")

    names, ratings = _solve_ratings(group)
    games_by_name = {name: 0 for name in names}
    observations = _observations(group)
    for subject, match in observations:
        games_by_name[subject] += match.games
        games_by_name[match.opponent] += match.games

    bootstrap = None
    warning = None
    if bootstrap_samples == 0:
        warning = "bootstrapを無効にしたため、95%区間と1位率は計算していません。"
    elif any(match.ptnml is None for _, match in observations):
        missing = ", ".join(
            f"{subject}対{match.opponent}"
            for subject, match in observations
            if match.ptnml is None
        )
        warning = (
            f"Ptnmlがない対戦を含むため、点推定のみです: {missing}"
        )
    else:
        bootstrap = _bootstrap(group, bootstrap_samples, seed)

    rows = []
    for player_index, name in enumerate(names):
        if bootstrap is None:
            lower = None
            upper = None
            first_place_rate = None
        else:
            samples_for_player = bootstrap[player_index]
            lower = _percentile(samples_for_player, 0.025)
            upper = _percentile(samples_for_player, 0.975)
            first_place_count = 0
            for sample_index in range(bootstrap_samples):
                sample_ratings = [
                    bootstrap[index][sample_index]
                    for index in range(len(names))
                ]
                if sample_ratings[player_index] == max(sample_ratings):
                    first_place_count += 1
            first_place_rate = first_place_count / bootstrap_samples

        rows.append(
            PlayerRating(
                name=name,
                rating=ratings[player_index],
                lower=lower,
                upper=upper,
                games=games_by_name[name],
                first_place_rate=first_place_rate,
            )
        )

    rows.sort(key=lambda player: player.rating, reverse=True)
    return TableAnalysis(
        table=group,
        players=tuple(rows),
        bootstrap_samples=bootstrap_samples if bootstrap is not None else 0,
        warning=warning,
    )


def analyze_table(
    table: ResultTable,
    *,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_RANDOM_SEED,
) -> TableAnalysis:
    """一つの表だけを解析する後方互換用の入口。"""

    group = ResultGroup(
        section=table.section,
        condition=table.condition,
        tables=(table,),
    )
    return analyze_group(
        group,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )


def format_markdown(analyses: Sequence[TableAnalysis]) -> str:
    lines = []
    for analysis in analyses:
        if lines:
            lines.append("")
        lines.append(
            f"## {analysis.table.section} / {analysis.table.condition}"
        )
        lines.append("")
        if analysis.warning:
            lines.append(f"> {analysis.warning}")
            lines.append("")
        elif analysis.bootstrap_samples:
            lines.append(
                f"Ptnmlのペア単位bootstrap "
                f"{analysis.bootstrap_samples:,}回。参加AIの平均Ratingを0とした。"
            )
            lines.append("")

        lines.append("| 順位 | AI | Rating | 95%区間 | 対局数 | 1位率 |")
        lines.append("|---:|---|---:|---:|---:|---:|")
        for rank, player in enumerate(analysis.players, start=1):
            interval = (
                f"{player.lower:+.2f} ～ {player.upper:+.2f}"
                if player.lower is not None and player.upper is not None
                else "—"
            )
            first_place_rate = (
                f"{100.0 * player.first_place_rate:.1f}%"
                if player.first_place_rate is not None
                else "—"
            )
            lines.append(
                f"| {rank} | {player.name} | {player.rating:+.2f} | "
                f"{interval} | {player.games:,} | {first_place_rate} |"
            )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "成績Markdownの勝–敗–引分とPtnmlから、合成PGNを作らずに"
            "Ordo相当の相対Ratingを計算します。"
        )
    )
    parser.add_argument("document", type=Path, help="入力するMarkdown文書")
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_BOOTSTRAP_SAMPLES,
        help=f"Ptnml bootstrap回数（既定: {DEFAULT_BOOTSTRAP_SAMPLES}）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"bootstrap乱数seed（既定: {DEFAULT_RANDOM_SEED}）",
    )
    args = parser.parse_args(argv)

    try:
        text = args.document.read_text(encoding="utf-8")
        tables = parse_result_tables(text)
        groups = group_result_tables(tables)
        analyses = [
            analyze_group(
                group,
                bootstrap_samples=args.samples,
                seed=args.seed + group_index,
            )
            for group_index, group in enumerate(groups)
        ]
    except (OSError, UnicodeError, MarkdownResultError) as error:
        parser.error(str(error))

    print(format_markdown(analyses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
