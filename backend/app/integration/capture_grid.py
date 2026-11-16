"""에브리타임 시간표 캡처에서 수업 칸의 위치를 픽셀로 재는 곳. 레인 B, #66.

모델은 칸 높이를 보고 시각을 짐작해 끝 시각을 정각·30분으로 뭉갠다(11/16 평가:
시각 정확 18.5%). 에브리타임 표는 모양이 일정해서 위치는 코드로 정확히 잴 수 있다.

- **색을 박아 두지 않는다.** 에브리타임은 테마로 칸 색이 바뀌고 다크 모드도 있다.
  배경색(가장 많은 색)과 격자선 색(배경과 조금 다른 회색 중 가장 많은 색)을 캡처마다
  잡고, 칸은 "배경과도 격자선과도 다른 픽셀"로 본다. 채도를 보지 않아 흑백 테마도 된다.
- 격자선을 가로·세로로 찾는다.
- 세로선 사이가 요일 열이다(첫 칸은 시각 열).
- 가로선 간격이 한 시간 높이다. 요일 머리 아래 선이 첫 시각이다.
- 열마다 색칠된(채도 높은) 줄을 이어 칸을 만든다. 색이 바뀌면 다른 칸이다.

여기서는 첫 시각의 **숫자**는 모른다(글자를 안 읽는다). 칸은 "첫 시각선부터 몇 분"으로
돌려주고, 몇 시인지는 모델이 읽은 수업과 맞춰 capture.py가 정한다.
**보조 수단이다.** 수업 목록은 모델 것이고, 여기서 잰 칸은 모델 칸의 시각을 다듬는 데만
쓴다(capture.merge). 격자를 못 찾으면 None — 모델이 읽은 시각을 그대로 쓴다.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from PIL import Image, UnidentifiedImageError

_LINE_TOL = 6  # 격자선 색에서 이만큼까지는 선
_BLOCK_MIN = 30  # 배경에서 이만큼 넘게 다르면 칸 후보(채널 최대 차)
_FILL_MIN = 0.6  # 칸 왼쪽 띠에서 칸 픽셀 비율이 이 이상인 줄을 칸으로 본다
_SPLIT = 18  # 붙은 두 칸의 색 차이. 흑백 테마에서 빨강·노랑이 비슷한 회색이 돼도 가른다
_MIN_HOUR_PX = 40
_MIN_BLOCK_MIN = 10  # 이보다 짧은 덩어리는 칸이 아니라 잡티


@dataclass(frozen=True)
class Block:
    weekday: int  # 0=월(첫 요일 열)
    start_off: float  # 첫 시각선부터 분
    end_off: float


@dataclass(frozen=True)
class Grid:
    days: int
    blocks: tuple[Block, ...]


def _runs(indices: np.ndarray) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for v in indices.tolist():
        if out and v - out[-1][1] <= 2:
            out[-1][1] = v
        else:
            out.append([v, v])
    return [(a, b) for a, b in out]


def _load(image: bytes) -> np.ndarray | None:
    try:
        with Image.open(io.BytesIO(image)) as im:
            return np.asarray(im.convert("RGB")).astype(np.int16)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _palette(px: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """(배경색, 격자선 색 후보들). 배경은 가장 많은 색. 선 후보는 배경과 조금(4~60)
    다른 무채색을 많은 순으로 — 아래 시트처럼 넓은 회색 면이 더 많을 수 있어서
    어느 것이 선인지는 measure가 세로선이 나오는지로 고른다."""
    flat = px[::3, ::3].reshape(-1, 3)
    colors, counts = np.unique(flat, axis=0, return_counts=True)
    bg = colors[counts.argmax()]
    diff = np.abs(colors - bg).max(axis=1)
    gray = (colors.max(axis=1) - colors.min(axis=1)) <= 8
    idx = np.where((diff >= 4) & (diff <= 60) & gray)[0]
    idx = idx[np.argsort(-counts[idx])][:6]
    return bg, [colors[i] for i in idx]


def _columns(line: np.ndarray) -> list[tuple[int, int]] | None:
    """세로선 → 선 위치들. 화면 세로를 길게 지나는 열을 선으로 본다.

    - 선이 2px에 번진 캡처(저해상도)는 이웃한 두 열을 합쳐 본다(둘 중 하나라도 선이면 선).
    - 칸이 선을 덮거나 표가 화면 일부만 차지하면 비율이 낮아서, 가장 진한 선(표 테두리)의
      비율에 견줘 판단한다.
    """
    height = line.shape[0]
    band = line[height // 6 : height - height // 6]
    pair = band[:, :-1] | band[:, 1:]
    ratio = pair.mean(axis=0)
    if ratio.max() < 0.3:
        return None
    xs = _runs(np.where(ratio >= max(0.2, ratio.max() * 0.3))[0])
    # 격자선은 얇다. 넓은 띠(배경·시트 면)가 잡혔으면 이 색은 선이 아니다.
    if len(xs) < 3 or any(b - a > 8 for a, b in xs):
        return None
    return xs


def _fill_day_lines(xs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """칸에 덮여 안 보이는 요일 경계선을 채운다. 에브리타임의 요일 열은 폭이 모두 같다.

    시각 열 오른쪽 선(둘째)부터 요일 경계 사이 간격 중 가장 짧은 것을 한 열 폭으로 보고,
    그 배수로 벌어진 곳에 선을 끼워 넣는다(갤럭시 캡처에서 목·금 사이 선이 칸에 덮였다).
    """
    if len(xs) < 3:
        return xs
    head, days = xs[:1], xs[1:]
    gaps = [b[0] - a[0] for a, b in pairwise(days)]
    width = min(gaps)
    if width < 20:
        return xs
    filled = [days[0]]
    for a, b in pairwise(days):
        k = round((b[0] - a[0]) / width)
        if k >= 2 and abs((b[0] - a[0]) / width - k) < 0.08:
            for i in range(1, k):
                x = round(a[0] + (b[0] - a[0]) * i / k)
                filled.append((x, x + (a[1] - a[0])))
        filled.append(b)
    return head + filled


def measure(image: bytes) -> Grid | None:
    px = _load(image)
    if px is None or px.shape[0] < 200 or px.shape[1] < 200:
        return None
    height = px.shape[0]
    bg, candidates = _palette(px)
    diff_bg = np.abs(px - bg).max(axis=2)
    # 선 후보 마스크들. 첫째는 "배경보다 조금 다른 무채색 전부" — 해상도가 낮은 캡처
    # (갤럭시 720px JPG)는 선이 2px에 걸쳐 237·241·242로 번져서 한 색으로는 일부만 잡힌다.
    # 나머지는 색 하나씩. 세로선이 가장 많이 나오는 마스크를 쓴다.
    grayish = (px.max(axis=2) - px.min(axis=2)) <= 10
    masks = [grayish & (diff_bg >= 6) & (diff_bg <= _BLOCK_MIN)]
    for line_rgb in candidates:
        # 배경과 가까우면 허용 오차를 줄인다(배경이 선으로 잡히지 않게)
        tol = min(_LINE_TOL, int(np.abs(line_rgb - bg).max()) // 2)
        masks.append(np.abs(px - line_rgb).max(axis=2) <= tol)
    best = None
    for mask in masks:
        found = _columns(mask)
        if found is not None and (best is None or len(found) > len(best[1])):
            best = (mask, found)
    if best is None:
        return None
    line, xs = best
    xs = _fill_day_lines(xs)
    # 첫 선 = 표 왼쪽 테두리, 둘째 = 시각 열 오른쪽, 나머지 = 요일 경계·오른쪽 테두리
    edges = [b for _, b in xs[1:]]
    columns = [(edges[i] + 1, xs[i + 2][0] - 1) for i in range(len(edges) - 1)]
    columns = [(a, b) for a, b in columns if b - a > 20]
    if not 1 <= len(columns) <= 7:
        return None
    left, right = xs[0][0], xs[-1][1]

    # 가로선: 표 폭의 절반 이상을 지나는 줄. 칸이 선을 덮으면 빠질 수 있다.
    ys = _runs(np.where(line[:, left:right].mean(axis=1) > 0.5)[0])
    if len(ys) < 3:
        return None
    tops = [a for a, _ in ys]
    diffs = sorted({b - a for a, b in pairwise(tops) if b - a >= _MIN_HOUR_PX})
    if not diffs:
        return None
    # 한 시간 높이: 선 사이 거리들을 가장 많이 정수배로 설명하는 값. 칸이 선을 덮어
    # 두 시간 간격이 섞이고, 표 위 테두리~요일 머리처럼 시간이 아닌 간격도 있다.
    pairs = [b - a for i, a in enumerate(tops) for b in tops[i + 1 :]]

    def explains(d: int) -> int:
        return sum(1 for p in pairs if abs(p / d - round(p / d)) < 0.02)

    hour = float(max(diffs, key=lambda d: (explains(d), d)))
    # 첫 시각선: 바로 다음 선이 한 시간의 1~3배 거리에 있는 첫 선. 표 위 테두리는
    # 다음 선(요일 머리 아래)까지 한 시간이 안 돼서 걸러진다. 멀리 있는 선과의
    # 배수만 보면 테두리가 우연히 맞을 수 있다.
    origin_line = None
    for (a, b), (next_a, _) in pairwise(ys):
        k = (next_a - a) / hour
        if 1 <= round(k) <= 3 and abs(k - round(k)) < 0.04:
            origin_line = (a, b)
            break
    if origin_line is None:
        return None
    origin = origin_line[1] + 1
    # 표 아래끝: 시각 열 오른쪽 세로선이 끝나는 곳. 이 선은 칸에 덮이지 않고 표 끝까지만
    # 이어진다. 화면 맨 아래 가로선을 쓰면 표 밖(온라인 강의 줄·학점계산기 카드)을 칸으로
    # 읽고(갤럭시), 시각선 배수로 찾으면 칸에 덮인 선 때문에 표가 짧아진다(아이폰).
    hour_line = line[:, max(0, xs[1][0] - 1) : xs[1][1] + 2].any(axis=1)
    bottom = origin
    while bottom < height and hour_line[bottom : bottom + 4].any():
        bottom += 1
    if bottom - origin < hour:
        bottom = height

    blocks: list[Block] = []
    # 칸 픽셀: 배경과 충분히 다르다(격자선은 배경과 _BLOCK_MIN 이하로만 달라 빠진다)
    paint = diff_bg > _BLOCK_MIN
    for day, (a, b) in enumerate(columns):
        # 칸 왼쪽 끝의 좁은 띠만 본다. 과목명 글씨(흰색)는 칸 왼쪽에서 조금 떨어져
        # 시작하므로 이 띠에는 색만 있다. 가운데를 보면 글씨 줄에서 칸이 끊긴다.
        inner_a, inner_b = a + 1, a + 1 + max(3, (b - a) // 50)
        strip = px[origin:bottom, inner_a:inner_b]
        filled = paint[origin:bottom, inner_a:inner_b].mean(axis=1) >= _FILL_MIN
        # 줄마다 대표 색(칸 픽셀의 중앙값). 색이 바뀌면 칸을 끊는다.
        start = None
        prev_color = None
        for y in range(len(filled) + 1):
            on = y < len(filled) and bool(filled[y])
            color = None
            if on:
                mask = paint[origin + y, inner_a:inner_b]
                color = np.median(strip[y][mask], axis=0)
            split = (
                on
                and start is not None
                and prev_color is not None
                and float(np.abs(color - prev_color).max()) > _SPLIT
            )
            if start is not None and (not on or split):
                blocks.append(Block(day, start * 60 / hour, y * 60 / hour))
                start = None
            if on and start is None:
                start = y
            prev_color = color if on else None
    blocks = [b for b in blocks if b.end_off - b.start_off >= _MIN_BLOCK_MIN]
    return Grid(days=len(columns), blocks=tuple(blocks))

