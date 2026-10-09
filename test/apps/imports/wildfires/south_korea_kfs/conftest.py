#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture builders for the Korea Forest Service import tests.

The release is written the way the service publishes it — **CP949**, the header
of :data:`~src.providers.south_korea_kfs.COLUMNS`, newest first — and the rows
reproduce the oddities of the real file: a province with a trailing space, a
cause text with a stray backtick, Sejong with no municipality, a city
neighbourhood with no township, an end before the start and an end in 2223.
"""

from __future__ import annotations

import csv
import io

from pathlib import Path

from src.providers.south_korea_kfs import COLUMNS


def fire(start: str = "2025-03-22 11:25", weekday: str = "토",
         end: str = "2025-03-22 18:40", office: str = "경북", province: str = "경북",
         municipality: str = "의성", township: str = "안계", village: str = "용기",
         code: str = "", detail: str = "논밭두렁소각", text: str = "논밭두렁소각",
         area: str = "0.5") -> list[str]:
    """One published row. Dates are given as ``YYYY-MM-DD HH:MM`` and split."""
    start_date, start_time = start.split(" ")
    end_date, end_time = end.split(" ")
    return [*start_date.split("-"), start_time, weekday,
            *end_date.split("-"), end_time,
            office, province, municipality, township, village,
            code, detail, text, area]


#: Every odd case of the real release, one row each, newest first.
ROWS = [
    # An ordinary fire, the Uiseong one in size.
    fire(area="52707.3"),
    # A cause text with a stray backtick, an end before the start (midnight).
    fire(start="2024-04-06 14:10", weekday="토", end="2024-04-06 00:00",
         office="충남", province="충남 ", municipality="천안 서북", township="성거",
         village="천흥", code="기", detail="기타(직접입력)", text="`전기누전",
         area="0.1"),
    # Sejong: no municipality. City neighbourhood: no township.
    fire(start="2023-03-11 13:00", weekday="토", end="2023-03-11 15:30",
         office="세종", province="세종", municipality="", township="",
         village="미곡", code="입", detail="기타(직접입력)", text="입산자실화추정",
         area="0.2"),
    # An end in 2223.
    fire(start="2022-01-01 00:24", weekday="토", end="2223-01-01 03:30",
         office="충남", province="충남", municipality="천안 서북", township="성거",
         village="천흥", code="입", detail="기타(직접입력)", text="입산자실화",
         area="0.3"),
]


def write_release(path: Path, rows: list[list[str]] | None = None,
                  header: tuple[str, ...] = COLUMNS, encoding: str = "cp949") -> Path:
    """Write a release file as the portal publishes it."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(ROWS if rows is None else rows)
    path.write_bytes(buffer.getvalue().encode(encoding))
    return path
