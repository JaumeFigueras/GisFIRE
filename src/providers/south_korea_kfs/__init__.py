#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Korea Forest Service — *산림청*.

Data model for the South Korean wildfire statistics, *산불통계데이터*, published by
the Korea Forest Service on the national open data portal as data.go.kr dataset
15121380: one CSV holding every fire of the recent years, one row per fire.

The first source in GisFIRE in Asia, and an **administrative** statistic like
:mod:`src.providers.greece_ffa` and :mod:`src.providers.spain_egif`: a record of
when a fire started and was put out, where it was filed, why it started and how
much burnt. There is no coordinate and no shape in any row.

The release
-----------

The 2025-09-12 release (``산불발생통계(20251110).csv``) holds **2,020 fires from
1 January 2022 to 11 September 2025**: 756 in 2022, 589 in 2023, 278 in 2024 and
397 in the part of 2025 it covers. 2022 agrees with the service's published
yearly total (756 fires, 24,797 ha). It is a recent-years file, not an archive,
and **the last year is partial**, so the next release revises it — which is why
an import replaces a year wholesale.

The file is **CP949**, the Windows Korean code page, with a header of the 18
names in :data:`COLUMNS`, ordered newest first. Nothing in a row identifies the
fire: no number, no code. The data dictionary that comes with it describes 30
columns; the twelve not in the CSV are derived ones (combined dates, durations,
an error flag and the standard administrative codes) that were never published.

Where
-----

Five names, as published and abbreviated:

``발생장소_관서``
    The office that filed the fire: a province (``경북``), a regional forest
    office (``남부``, *Southern*) or a KFS institute — :data:`OFFICES`.
``발생장소_시도``
    The province, abbreviated (``경북`` for 경상북도) — :data:`PROVINCES`. One
    value is written with a trailing space, ``충남`` followed by a blank.
``발생장소_시군구``
    The municipality, without its 시/군/구 suffix. City districts are written
    *city district* (``천안 서북``). **Blank for Sejong**, which has no municipal
    tier, and on two other rows by omission.
``발생장소_읍면``
    The township. **Blank for a city neighbourhood** (동), which has no township
    tier: blank here is a fact about the place, not missing data.
``발생장소_동리``
    The village or neighbourhood.

Each is stored trimmed and, beside it, romanized by :func:`romanize`.

When
----

The start and the end of suppression are each published as year, month, day and
``HH:MM``, in Korean local time — :data:`DEFAULT_TIME_ZONE`, one zone for the
country and no daylight saving since 1988. The start's weekday is published too,
and agrees with the date on every row.

**Fourteen ends are wrong.** Twelve fires end before they start, every one of
them at 00:00 on the start day — a missing time typed as midnight — and two end
in 2055 and 2223. They are stored with no end and the reason in
:attr:`~src.providers.south_korea_kfs.wildfire.KfsWildfire.end_date_problem`; see
:func:`end_date_problem`.

Why
---

Three columns, of which the third is the one that says anything:

``발생원인_구분``
    A one-letter code: ``입`` forest visitor, ``쓰`` waste burning, ``담``
    cigarette, ``기`` other — :data:`CAUSE_CATEGORIES`. Blank on 294 rows.
``발생원인_세부원인``
    A category from :data:`CAUSE_DETAILS`. **Blank code and specific category
    go together**: the code is blank exactly when this is not
    ``기타(직접입력)``, *other (free text)* — which it is on 1,479 rows, 73%.
``발생원인_기타``
    The cause in words. 455 spellings, typos included; 453 after
    :func:`normalise_cause`.

All three are stored as published. The free text is also translated and
classified by :mod:`src.providers.south_korea_kfs.causes` into one of the
eighteen :data:`CAUSE_CLASSES`, and that class into one of the four
:data:`FIRE_CAUSES` the New Zealand WOD uses, so the two countries can be compared.
A spelling the table does not know is an error, not *unknown*: see :func:`cause`.

403 texts — one fire in five — give their cause as suspected (``추정``, ``의심``)
or under police investigation (``수사중``); :func:`is_suspected` says which.

How much
--------

``피해면적_합계`` is the burnt area in hectares, 0.01 to 52,707.3, never blank and
never negative. The two Uiseong fires of 22 March 2025 are 99,282.5 ha between
them — 74% of all the area in the release — and, like every row, are filed at the
place they started, although they burnt into four other municipalities.
"""

from __future__ import annotations

import datetime
import re

#: Short name of the provider.
PROVIDER_NAME = "KFS"

#: Full name of the provider.
PROVIDER_FULL_NAME = "Korea Forest Service (산림청)"

#: The product: the dataset's own title on data.go.kr.
PROVIDER_PRODUCT = "산불통계데이터"

#: The dataset's page on the national open data portal.
PROVIDER_URL = "https://www.data.go.kr/data/15121380/fileData.do"

#: The zone every published time is in. One for the whole country, no daylight
#: saving since 1988.
DEFAULT_TIME_ZONE = "Asia/Seoul"

#: Encodings a release is tried in, in order. The portal's files are CP949; a
#: UTF-8 copy (re-saved by hand, or a future release) is read as well, with or
#: without a byte-order mark.
ENCODINGS = ("utf-8-sig", "cp949")

#: The published header, in order.
COLUMNS = (
    "발생일시_년", "발생일시_월", "발생일시_일", "발생일시_시간", "발생일시_요일",
    "진화종료시간_년", "진화종료시간_월", "진화종료시간_일", "진화종료시간_시간",
    "발생장소_관서", "발생장소_시도", "발생장소_시군구", "발생장소_읍면", "발생장소_동리",
    "발생원인_구분", "발생원인_세부원인", "발생원인_기타",
    "피해면적_합계",
)

#: Published weekday to its ISO number (Monday 1).
WEEKDAYS = {"월": 1, "화": 2, "수": 3, "목": 4, "금": 5, "토": 6, "일": 7}

#: Published province abbreviation to its English name.
PROVINCES = {
    "강원": "Gangwon", "경기": "Gyeonggi", "경남": "Gyeongnam (South Gyeongsang)",
    "경북": "Gyeongbuk (North Gyeongsang)", "광주": "Gwangju", "대구": "Daegu",
    "대전": "Daejeon", "부산": "Busan", "서울": "Seoul", "세종": "Sejong",
    "울산": "Ulsan", "인천": "Incheon", "전남": "Jeonnam (South Jeolla)",
    "전북": "Jeonbuk (North Jeolla)", "제주": "Jeju",
    "충남": "Chungnam (South Chungcheong)", "충북": "Chungbuk (North Chungcheong)",
}

#: Published filing office to its English name: a province, or one of the
#: service's own offices and institutes.
OFFICES = dict(PROVINCES, **{
    "북부": "KFS Northern Regional Forest Office",
    "남부": "KFS Southern Regional Forest Office",
    "중부": "KFS Central Regional Forest Office",
    "동부": "KFS Eastern Regional Forest Office",
    "서부": "KFS Western Regional Forest Office",
    "과학원": "National Institute of Forest Science",
    "수목원": "Korea National Arboretum",
})

#: ``발생원인_구분`` to its meaning.
CAUSE_CATEGORIES = {
    "입": "Forest visitor negligence", "쓰": "Waste burning",
    "담": "Cigarette", "기": "Other",
}

#: ``발생원인_세부원인`` to its meaning.
CAUSE_DETAILS = {
    "기타(직접입력)": "Other (free text)", "낙뢰": "Lightning",
    "논밭두렁소각": "Rice-paddy and field-edge burning",
    "농산폐기물소각": "Agricultural waste burning", "담뱃불실화": "Cigarette",
    "방화": "Arson", "성묘객실화": "Grave visitor negligence",
    "쓰레기소각": "Waste burning", "어린이불장난": "Children playing with fire",
    "작업장실화": "Work site negligence", "주택화재비화": "Spread from house fire",
}

#: The detailed cause meaning *see the free text*.
CAUSE_DETAIL_FREE_TEXT = "기타(직접입력)"

# --- Cause classes ------------------------------------------------------------

#: Forest visitors and hikers, anglers, campers: carelessness in the forest.
CLASS_VISITOR = "visitor"
#: Unknown, or under investigation with no cause suspected.
CLASS_UNKNOWN = "unknown"
#: Burning household or other waste.
CLASS_WASTE_BURNING = "waste_burning"
#: A cigarette.
CLASS_CIGARETTE = "cigarette"
#: Dumped ash, wood boilers and stoves, campfires and other embers.
CLASS_EMBERS_ASH = "embers_ash"
#: Burning fields, paddy edges and agricultural waste.
CLASS_AGRICULTURAL_BURNING = "agricultural_burning"
#: Spread from a building, greenhouse or shed fire.
CLASS_STRUCTURE_FIRE = "structure_fire"
#: Welding, grinders, brush cutters and other work.
CLASS_WORK_MACHINERY = "work_machinery"
#: Power lines, transformers and electrical faults.
CLASS_POWER_ELECTRICAL = "power_electrical"
#: Visitors to ancestral graves.
CLASS_GRAVE_VISITOR = "grave_visitor"
#: Arson.
CLASS_ARSON = "arson"
#: Beekeepers' smokers and hive work.
CLASS_BEEKEEPING = "beekeeping"
#: Military firing, flares and aircraft.
CLASS_MILITARY_AIRCRAFT = "military_aircraft"
#: Vehicles.
CLASS_VEHICLE = "vehicle"
#: Anything else.
CLASS_OTHER = "other"
#: Lightning.
CLASS_LIGHTNING = "lightning"
#: Children playing with fire.
CLASS_CHILDREN = "children"
#: A fire that rekindled from an earlier one.
CLASS_REKINDLE = "rekindle"

#: Every class :mod:`src.providers.south_korea_kfs.causes` assigns.
CAUSE_CLASSES = (
    CLASS_VISITOR, CLASS_UNKNOWN, CLASS_WASTE_BURNING, CLASS_CIGARETTE,
    CLASS_EMBERS_ASH, CLASS_AGRICULTURAL_BURNING, CLASS_STRUCTURE_FIRE,
    CLASS_WORK_MACHINERY, CLASS_POWER_ELECTRICAL, CLASS_GRAVE_VISITOR, CLASS_ARSON,
    CLASS_BEEKEEPING, CLASS_MILITARY_AIRCRAFT, CLASS_VEHICLE, CLASS_OTHER,
    CLASS_LIGHTNING, CLASS_CHILDREN, CLASS_REKINDLE,
)

# --- Fire causes, the classes shared with the other providers -----------------

#: Lightning.
CAUSE_LIGHTNING = "lightning"
#: Natural but not lightning. No Korean fire is.
CAUSE_NATURAL = "natural"
#: People.
CAUSE_HUMAN = "human"
#: Not known.
CAUSE_UNKNOWN = "unknown"

#: The four classes, the same as :data:`src.providers.new_zealand_wod.FIRE_CAUSES`.
FIRE_CAUSES = (CAUSE_LIGHTNING, CAUSE_NATURAL, CAUSE_HUMAN, CAUSE_UNKNOWN)

#: A rekindled fire's cause is the earlier fire's, which the row does not say.
FIRE_CAUSE_BY_CLASS = {
    cause_class: CAUSE_HUMAN for cause_class in CAUSE_CLASSES
} | {
    CLASS_LIGHTNING: CAUSE_LIGHTNING,
    CLASS_UNKNOWN: CAUSE_UNKNOWN,
    CLASS_REKINDLE: CAUSE_UNKNOWN,
}

#: Words in a cause text saying the cause is suspected (추정, 의심) or under
#: police investigation (수사중) rather than established.
SUSPECTED_MARKERS = ("추정", "의심", "수사중")

# --- End dates ------------------------------------------------------------------

#: The fire ends before it starts.
END_BEFORE_START = "extinguish_before_start"
#: The end's year is neither the start's nor the next.
END_INVALID_YEAR = "extinguish_year_invalid"

#: The reasons a published end is not stored.
END_DATE_PROBLEMS = (END_BEFORE_START, END_INVALID_YEAR)


class UnmappedCauseError(ValueError):
    """A ``발생원인_기타`` text that :mod:`src.providers.south_korea_kfs.causes` does not list."""


def clean(value: str | None) -> str | None:
    """A published name as stored: trimmed, or ``None`` when blank."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalise_cause(value: str) -> str:
    """The key a published cause text is looked up by.

    Trimmed of whitespace and of backticks: one text is published with a leading
    space and one as ``\\`전기누전``, and they differ from other spellings in that
    and nothing else. Spellings that differ in anything more are listed
    separately rather than guessed together.
    """
    return value.strip().strip("`").strip()


def cause(value: str) -> tuple[str, str]:
    """Translate and classify a published cause text.

    Returns
    -------
    tuple of str
        The English translation and one of :data:`CAUSE_CLASSES`.

    Raises
    ------
    UnmappedCauseError
        For a text the table does not list. Deliberately an error rather than
        *unknown*: a new release that adds a spelling must have it classified by a
        person, because quietly counting a new lightning text as unknown is the
        mistake the class exists to prevent.
    """
    from src.providers.south_korea_kfs.causes import CAUSES

    try:
        return CAUSES[normalise_cause(value)]
    except KeyError:
        raise UnmappedCauseError(f"unmapped KFS cause text: {value!r}") from None


def fire_cause(cause_class: str) -> str:
    """The shared fire cause of one of :data:`CAUSE_CLASSES`."""
    return FIRE_CAUSE_BY_CLASS[cause_class]


def is_suspected(value: str) -> bool:
    """Whether a cause text gives its cause as suspected rather than established."""
    return any(marker in value for marker in SUSPECTED_MARKERS)


def end_date_problem(start: datetime.datetime,
                     end: datetime.datetime | None) -> str | None:
    """Why a published end cannot be stored, or ``None`` if it can.

    The end's year must be the start's or the next one — 2055 and 2223 are not —
    and the end must not come before the start. ``end`` is ``None`` when the
    published parts are not a date at all, which counts as an invalid year.
    """
    if end is None or end.year not in (start.year, start.year + 1):
        return END_INVALID_YEAR
    if end < start:
        return END_BEFORE_START
    return None


# --- Revised Romanization -----------------------------------------------------

_INITIAL = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj",
            "ch", "k", "t", "p", "h")
_MEDIAL = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo",
           "u", "wo", "we", "wi", "yu", "eu", "ui", "i")
#: A final consonant as pronounced before a consonant or at the end of a word.
_FINAL = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l",
          "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t")
#: A final consonant carried over onto a following silent ㅇ.
_LIAISON = ("", "g", "kk", "ks", "n", "nj", "n", "d", "r", "lg", "lm", "lb", "ls", "lt",
            "lp", "r", "m", "b", "ps", "s", "ss", "ng", "j", "ch", "k", "t", "p", "")
_INITIAL_N, _INITIAL_R, _INITIAL_M, _INITIAL_SILENT = 2, 5, 6, 11

_HANGUL_FIRST = 0xAC00
_HANGUL_COUNT = 11172


def _syllables(word: str) -> list[tuple[int, int, int] | str]:
    """Split a word into (initial, medial, final) jamo indices, other characters as is."""
    out: list[tuple[int, int, int] | str] = []
    for character in word:
        code = ord(character) - _HANGUL_FIRST
        if 0 <= code < _HANGUL_COUNT:
            out.append((code // 588, (code % 588) // 28, code % 28))
        else:
            out.append(character)
    return out


def _romanize_word(word: str) -> str:
    syllables = _syllables(word)
    parts = []
    for index, syllable in enumerate(syllables):
        if isinstance(syllable, str):
            parts.append(syllable)
            continue
        initial, medial, final = syllable
        previous = syllables[index - 1] if index > 0 else None
        following = syllables[index + 1] if index + 1 < len(syllables) else None
        previous = None if isinstance(previous, str) else previous
        following = None if isinstance(following, str) else following

        # The initial, as changed by the previous syllable's final.
        if previous is None:
            head = _INITIAL[initial]
        else:
            previous_final = _FINAL[previous[2]]
            if initial == _INITIAL_SILENT:
                # After anything but ng the final has already been carried over.
                head = ""
            elif initial == _INITIAL_R:
                head = "l" if previous_final in ("l", "n") else ("n" if previous_final else "r")
            elif initial == _INITIAL_N and previous_final == "l":
                head = "l"
            else:
                head = _INITIAL[initial]

        # The final, as changed by the next syllable's initial.
        coda = _FINAL[final]
        if following is not None:
            next_initial = following[0]
            if next_initial == _INITIAL_SILENT and final and coda != "ng":
                coda = _LIAISON[final]
            elif next_initial in (_INITIAL_N, _INITIAL_M):
                coda = {"k": "ng", "t": "n", "p": "m"}.get(coda, coda)
            elif next_initial == _INITIAL_R:
                coda = {"k": "ng", "t": "n", "p": "m", "n": "l"}.get(coda, coda)
        parts.append(head + _MEDIAL[medial] + coda)
    text = "".join(parts)
    return text[:1].upper() + text[1:]


def romanize(value: str | None) -> str | None:
    """A place name in the Revised Romanization of Korean, or ``None`` for none.

    Applied by rule — liaison, nasalisation and ㄹ assimilation — word by word,
    each word capitalised: ``천안 서북`` is ``Cheonan Seobuk``. The rules cover
    every name the release publishes that was checked against its official
    spelling, but a name whose signposted form follows an exception (palatalisation,
    tensing written into the name) may differ from it. Characters that are not
    Hangul syllables, such as the digits of ``남산2리``, are kept as they are.
    """
    name = clean(value)
    if name is None:
        return None
    return " ".join(_romanize_word(word) for word in re.split(r"\s+", name))
