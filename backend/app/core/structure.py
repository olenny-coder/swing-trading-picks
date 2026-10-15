"""Breakout structure detection.

The structures recognised here are the ones a swing trader actually marks up:

| Kind | What it is |
|---|---|
| ``BOS`` | Break of structure — a close beyond the prior swing in the direction of the trend |
| ``CHOCH`` | Change of character — the first close beyond the opposing swing, against the prior trend |
| ``RANGE`` | Range / consolidation breakout — a close out of a tight box |
| ``FLAG`` | Flag or pennant breakout — a shallow pause after an impulse, then a break |
| ``TRENDLINE`` | Trendline break — a close through a line drawn across two swing points |
| ``SUPPLY_DEMAND_FLIP`` | A broken level that was retested and held (resistance became support, or the reverse) |

Every detector reads **closed candles only** and reports the level it broke, so a
chart can mark it exactly. Detection is descriptive, not predictive: a structure
on its own is not a trade. It becomes one only in combination with a Fair Value
Gap — see ``fvg_strategy.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .fvg import BUY, SELL

#: Candles either side required to confirm a fractal pivot.
SWING_K = 2
#: How many recent candles a break may have happened in and still count.
STRUCTURE_SCAN = 25
#: Candles that make up a consolidation box.
RANGE_WINDOW = 12
#: A box taller than this multiple of Average True Range is not "tight".
RANGE_MAX_ATR = 3.0
#: The impulse candle of a flag must be at least this multiple of Average True Range.
POLE_MIN_ATR = 1.5
#: A flag may retrace no more than this share of its pole.
FLAG_MAX_RETRACE = 0.5
#: Minimum candles in the pause of a flag.
FLAG_MIN_BARS = 3

KIND_LABELS = {
    "BOS": "Break of structure",
    "CHOCH": "Change of character",
    "RANGE": "Range breakout",
    "FLAG": "Flag breakout",
    "TRENDLINE": "Trendline break",
    "SUPPLY_DEMAND_FLIP": "Supply/demand flip",
}

#: How much each structure contributes to confidence on its own (0..1).
KIND_QUALITY = {
    "BOS": 0.80,
    "CHOCH": 0.95,          # a fresh change of character is the strongest turn
    "RANGE": 0.75,
    "FLAG": 0.70,
    "TRENDLINE": 0.65,
    "SUPPLY_DEMAND_FLIP": 0.90,
}


@dataclass
class BreakoutStructure:
    kind: str
    direction: str
    level: float
    confirmed_index: int
    confirmed_date: date
    detail: str
    #: "horizontal" for a level, "trendline" for a sloped line.
    level_kind: str = "horizontal"
    #: Two (date, price) points when the structure is a trendline.
    line: tuple[tuple[date, float], tuple[date, float]] | None = None
    #: (start_date, end_date, top, bottom) when the structure is a box.
    box: tuple[date, date, float, float] | None = None
    retested: bool = False

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    @property
    def quality(self) -> float:
        score = KIND_QUALITY.get(self.kind, 0.5)
        return min(1.0, score + (0.05 if self.retested else 0.0))

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "direction": self.direction,
            "level": round(self.level, 4),
            "level_kind": self.level_kind,
            "confirmed_date": self.confirmed_date.isoformat(),
            "detail": self.detail,
            "retested": self.retested,
            "line": [
                {"date": d.isoformat(), "price": round(p, 4)} for d, p in (self.line or ())
            ]
            or None,
            "box": (
                {
                    "start": self.box[0].isoformat(),
                    "end": self.box[1].isoformat(),
                    "top": round(self.box[2], 4),
                    "bottom": round(self.box[3], 4),
                }
                if self.box
                else None
            ),
        }


@dataclass
class SwingPoints:
    highs: list[int] = field(default_factory=list)
    lows: list[int] = field(default_factory=list)


def swing_indices(highs: list[float], lows: list[float], k: int = SWING_K) -> SwingPoints:
    """Fractal swing highs/lows confirmed by ``k`` candles either side."""
    sh: list[int] = []
    sl: list[int] = []
    for i in range(k, len(highs) - k):
        hwin = highs[i - k : i + k + 1]
        if highs[i] == max(hwin) and hwin.count(highs[i]) == 1:
            sh.append(i)
        lwin = lows[i - k : i + k + 1]
        if lows[i] == min(lwin) and lwin.count(lows[i]) == 1:
            sl.append(i)
    return SwingPoints(highs=sh, lows=sl)


def trend_before(bars: list, swings: SwingPoints, upto: int) -> str:
    """Trend implied by the swings that existed before ``upto``."""
    hs = [j for j in swings.highs if j < upto][-2:]
    ls = [j for j in swings.lows if j < upto][-2:]
    up = down = 0
    if len(hs) == 2:
        up += int(bars[hs[-1]].high > bars[hs[-2]].high)
        down += int(bars[hs[-1]].high < bars[hs[-2]].high)
    if len(ls) == 2:
        up += int(bars[ls[-1]].low > bars[ls[-2]].low)
        down += int(bars[ls[-1]].low < bars[ls[-2]].low)
    if up > down:
        return "up"
    if down > up:
        return "down"
    return "range"


def detect_bos_choch(bars: list, swings: SwingPoints, scan: int = STRUCTURE_SCAN):
    """Most recent close beyond a confirmed swing."""
    best = None
    for i in range(max(1, len(bars) - scan), len(bars)):
        prior_sh = [j for j in swings.highs if j <= i - SWING_K]
        prior_sl = [j for j in swings.lows if j <= i - SWING_K]

        if prior_sh:
            j = prior_sh[-1]
            if bars[i].close > bars[j].high:
                trend = trend_before(bars, swings, j)
                best = BreakoutStructure(
                    kind="CHOCH" if trend == "down" else "BOS",
                    direction=BUY,
                    level=bars[j].high,
                    confirmed_index=i,
                    confirmed_date=bars[i].date,
                    detail=(
                        f"Closed at {bars[i].close:.2f}, above the swing high of "
                        f"{bars[j].high:.2f} set on {bars[j].date.isoformat()}"
                    ),
                )
        if prior_sl:
            j = prior_sl[-1]
            if bars[i].close < bars[j].low:
                trend = trend_before(bars, swings, j)
                best = BreakoutStructure(
                    kind="CHOCH" if trend == "up" else "BOS",
                    direction=SELL,
                    level=bars[j].low,
                    confirmed_index=i,
                    confirmed_date=bars[i].date,
                    detail=(
                        f"Closed at {bars[i].close:.2f}, below the swing low of "
                        f"{bars[j].low:.2f} set on {bars[j].date.isoformat()}"
                    ),
                )
    return best


def detect_range_breakout(
    bars: list, atr_values: list[float | None], scan: int = STRUCTURE_SCAN, window: int = RANGE_WINDOW
):
    """A close out of a tight box."""
    for i in range(len(bars) - 1, max(window, len(bars) - scan) - 1, -1):
        a = atr_values[i] or 0.0
        if a <= 0:
            continue
        box = bars[i - window : i]
        top = max(b.high for b in box)
        bottom = min(b.low for b in box)
        if top <= bottom or (top - bottom) > RANGE_MAX_ATR * a:
            continue
        span = (box[0].date, box[-1].date, top, bottom)
        close = bars[i].close
        if close > top:
            return BreakoutStructure(
                kind="RANGE",
                direction=BUY,
                level=top,
                confirmed_index=i,
                confirmed_date=bars[i].date,
                detail=(
                    f"Closed at {close:.2f}, out of a {window}-candle box between "
                    f"{bottom:.2f} and {top:.2f}"
                ),
                box=span,
            )
        if close < bottom:
            return BreakoutStructure(
                kind="RANGE",
                direction=SELL,
                level=bottom,
                confirmed_index=i,
                confirmed_date=bars[i].date,
                detail=(
                    f"Closed at {close:.2f}, out of a {window}-candle box between "
                    f"{bottom:.2f} and {top:.2f}"
                ),
                box=span,
            )
    return None


def detect_flag_breakout(bars: list, atr_values: list[float | None], scan: int = STRUCTURE_SCAN):
    """An impulse, a shallow pause, then a break out of the pause."""
    for i in range(len(bars) - 1, max(3, len(bars) - scan) - 1, -1):
        for p in range(i - FLAG_MIN_BARS - 1, max(0, i - 30) - 1, -1):
            a = atr_values[p] or 0.0
            if a <= 0:
                continue
            body = abs(bars[p].close - bars[p].open)
            if body < POLE_MIN_ATR * a:
                continue
            up = bars[p].close > bars[p].open
            pause = bars[p + 1 : i]
            if len(pause) < FLAG_MIN_BARS:
                continue
            top = max(b.high for b in pause)
            bottom = min(b.low for b in pause)
            if (top - bottom) > body:
                continue
            if up:
                if bars[p].close - bottom > FLAG_MAX_RETRACE * body:
                    continue
                if bars[i].close > top:
                    return BreakoutStructure(
                        kind="FLAG",
                        direction=BUY,
                        level=top,
                        confirmed_index=i,
                        confirmed_date=bars[i].date,
                        detail=(
                            f"Impulse of {body:.2f} on {bars[p].date.isoformat()}, "
                            f"{len(pause)}-candle pause, then a close at {bars[i].close:.2f} "
                            f"above {top:.2f}"
                        ),
                    )
            else:
                if top - bars[p].close > FLAG_MAX_RETRACE * body:
                    continue
                if bars[i].close < bottom:
                    return BreakoutStructure(
                        kind="FLAG",
                        direction=SELL,
                        level=bottom,
                        confirmed_index=i,
                        confirmed_date=bars[i].date,
                        detail=(
                            f"Impulse of {body:.2f} on {bars[p].date.isoformat()}, "
                            f"{len(pause)}-candle pause, then a close at {bars[i].close:.2f} "
                            f"below {bottom:.2f}"
                        ),
                    )
    return None


def detect_trendline_break(bars: list, swings: SwingPoints, scan: int = STRUCTURE_SCAN):
    """A close through a line drawn across the last two swing points."""
    hs = swings.highs[-2:]
    if len(hs) == 2 and bars[hs[1]].high < bars[hs[0]].high:
        slope = (bars[hs[1]].high - bars[hs[0]].high) / (hs[1] - hs[0])
        for i in range(max(hs[1] + 1, len(bars) - scan), len(bars)):
            line = bars[hs[1]].high + slope * (i - hs[1])
            if bars[i].close > line:
                return BreakoutStructure(
                    kind="TRENDLINE",
                    direction=BUY,
                    level=line,
                    confirmed_index=i,
                    confirmed_date=bars[i].date,
                    detail=(
                        f"Closed at {bars[i].close:.2f}, through the falling trendline "
                        f"running from {bars[hs[0]].date.isoformat()}"
                    ),
                    level_kind="trendline",
                    line=((bars[hs[0]].date, bars[hs[0]].high), (bars[i].date, line)),
                )

    ls = swings.lows[-2:]
    if len(ls) == 2 and bars[ls[1]].low > bars[ls[0]].low:
        slope = (bars[ls[1]].low - bars[ls[0]].low) / (ls[1] - ls[0])
        for i in range(max(ls[1] + 1, len(bars) - scan), len(bars)):
            line = bars[ls[1]].low + slope * (i - ls[1])
            if bars[i].close < line:
                return BreakoutStructure(
                    kind="TRENDLINE",
                    direction=SELL,
                    level=line,
                    confirmed_index=i,
                    confirmed_date=bars[i].date,
                    detail=(
                        f"Closed at {bars[i].close:.2f}, through the rising trendline "
                        f"running from {bars[ls[0]].date.isoformat()}"
                    ),
                    level_kind="trendline",
                    line=((bars[ls[0]].date, bars[ls[0]].low), (bars[i].date, line)),
                )
    return None


def detect_supply_demand_flip(
    bars: list, swings: SwingPoints, atr_values: list[float | None], scan: int = STRUCTURE_SCAN
):
    """A broken level that price came back to and held."""
    n = len(bars)

    for j in reversed(swings.highs):
        if j > n - 3:
            continue
        level = bars[j].high
        brk = next((i for i in range(j + SWING_K + 1, n) if bars[i].close > level), None)
        if brk is None or brk >= n - 1 or n - brk > scan + 1:
            continue
        a = atr_values[brk] or 0.0
        if a <= 0:
            continue
        after = bars[brk + 1 : n]
        if not after:
            continue
        retest_idx = next(
            (k for k, b in enumerate(after, start=brk + 1) if b.low <= level + 0.5 * a), None
        )
        if retest_idx is not None and bars[-1].close > level:
            return BreakoutStructure(
                kind="SUPPLY_DEMAND_FLIP",
                direction=BUY,
                level=level,
                # Dated to the retest, not to today: a flip is a state, and
                # stamping it with the last candle would make it outrank every
                # genuinely fresh break.
                confirmed_index=retest_idx,
                confirmed_date=bars[retest_idx].date,
                detail=(
                    f"Resistance at {level:.2f} from {bars[j].date.isoformat()} was broken, "
                    f"retested and held"
                ),
                retested=True,
            )

    for j in reversed(swings.lows):
        if j > n - 3:
            continue
        level = bars[j].low
        brk = next((i for i in range(j + SWING_K + 1, n) if bars[i].close < level), None)
        if brk is None or brk >= n - 1 or n - brk > scan + 1:
            continue
        a = atr_values[brk] or 0.0
        if a <= 0:
            continue
        after = bars[brk + 1 : n]
        if not after:
            continue
        retest_idx = next(
            (k for k, b in enumerate(after, start=brk + 1) if b.high >= level - 0.5 * a), None
        )
        if retest_idx is not None and bars[-1].close < level:
            return BreakoutStructure(
                kind="SUPPLY_DEMAND_FLIP",
                direction=SELL,
                level=level,
                confirmed_index=retest_idx,
                confirmed_date=bars[retest_idx].date,
                detail=(
                    f"Support at {level:.2f} from {bars[j].date.isoformat()} was broken, "
                    f"retested and failed"
                ),
                retested=True,
            )

    return None


def detect_structures(
    bars: list, atr_values: list[float | None], swings: SwingPoints | None = None
) -> list[BreakoutStructure]:
    """Every structure currently visible, newest confirmation first."""
    if len(bars) < SWING_K * 2 + 3:
        return []
    swings = swings or swing_indices(
        [b.high for b in bars], [b.low for b in bars]
    )
    found = [
        detect_supply_demand_flip(bars, swings, atr_values),
        detect_bos_choch(bars, swings),
        detect_flag_breakout(bars, atr_values),
        detect_range_breakout(bars, atr_values),
        detect_trendline_break(bars, swings),
    ]
    live = [s for s in found if s is not None]
    live.sort(key=lambda s: s.confirmed_index, reverse=True)
    return live
