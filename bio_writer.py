"""Utilities to build brief genealogy biographies following a strict format.

This module exposes :func:`build_biography` which accepts a dictionary with
information about an ancestor and their relationships and returns a formatted
string ready to be pasted elsewhere.

The implementation purposely avoids external dependencies and relies only on
Python's standard library. Dates are expected in ISO format (``YYYY-MM-DD``)
or as a plain year string (``YYYY``). Approximate dates (e.g. ``"about 1929"``)
are preserved as is when provided.
"""

from __future__ import annotations

# No external libraries are required; only the standard library is used.
from datetime import date
import re
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# English month names (avoid locale-dependent %B)
# ---------------------------------------------------------------------------
_MONTHS_EN = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_iso_date(value: str) -> Optional[date]:
    """Return ``date`` if ``value`` is in ``YYYY-MM-DD`` format, else ``None``."""
    if not value:
        return None
    try:
        year, month, day = map(int, value.split("-"))
        return date(year, month, day)
    except Exception:
        return None


def _extract_year(value: Optional[str]) -> Optional[int]:
    """Extract the first four-digit year from ``value`` if present."""
    if not value:
        return None
    match = re.search(r"(\d{4})", value)
    if match:
        return int(match.group(1))
    return None


def format_date_long(value: str) -> str:
    """Return a human readable date (English months).
    ``value`` may be ``YYYY-MM-DD`` or ``YYYY``. Approximate textual values are
    returned unchanged.
    """
    dt = _parse_iso_date(value)
    if dt:
        return f"{dt.day} {_MONTHS_EN[dt.month]} {dt.year}"
    if re.fullmatch(r"\d{4}", value):
        return value
    return value


# ---------------------------------------------------------------------------
# Age calculations
# ---------------------------------------------------------------------------

def calc_age_exact(birth: date, event: date) -> int:
    """Return the age in full years between ``birth`` and ``event``."""
    years = event.year - birth.year
    if (event.month, event.day) < (birth.month, birth.day):
        years -= 1
    return years


def calc_age_approx(birth_year: int, event_year: int) -> int:
    """Return the difference in years between ``birth_year`` and ``event_year``."""
    return event_year - birth_year


def format_age_exact(n: int) -> str:
    return str(n)


def format_age_approx(n: int) -> str:
    return f"approximately {n}"


# ---------------------------------------------------------------------------
# Pronouns and ordinals
# ---------------------------------------------------------------------------

def _pronouns(gender: Optional[str]) -> Dict[str, str]:
    """Return a dictionary with pronouns for ``gender``.
    Gender may be ``'M'``/``'male'`` or ``'F'``/``'female'``. Any other value → neutral.
    """
    if gender and gender.lower().startswith("m"):
        return {"subj": "he", "obj": "him", "poss": "his"}
    if gender and gender.lower().startswith("f"):
        return {"subj": "she", "obj": "her", "poss": "her"}
    return {"subj": "they", "obj": "them", "poss": "their"}


_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
}

def _ordinal(n: int) -> str:
    return _ORDINALS.get(n, f"{n}th")


# ---------------------------------------------------------------------------
# Formatting blocks
# ---------------------------------------------------------------------------

def _describe_date(date_str: Optional[str], approx: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Return (phrase, year) describing the date or approx."""
    if date_str:
        dt = _parse_iso_date(date_str)
        if dt:
            return f"on {format_date_long(date_str)}", dt.year
        year = _extract_year(date_str)
        if year:
            return f"in {year}", year
    if approx:
        year = _extract_year(approx)
        if re.fullmatch(r"\d{4}", approx.strip()):
            return f"in {approx.strip()}", year
        return approx, year
    return None, None


def _format_birth_block(person: dict, person_pron: Dict[str, str]) -> str:
    birth = person.get("birth", {})
    sentence = f"{person['name']} was born"
    date_str = birth.get("date")
    place = birth.get("place")

    if date_str:
        dt = _parse_iso_date(date_str)
        if dt:
            sentence += f" on {format_date_long(date_str)}"
        else:
            year = _extract_year(date_str)
            if year:
                sentence += f" in {year}"
    if place:
        if date_str:
            sentence += f", in {place}"
        else:
            sentence += f" in {place}"
    sentence += "."
    return sentence


def _format_parents_block(person: dict, person_pron: Dict[str, str]) -> str:
    parents = person.get("parents") or {}
    father = parents.get("father")
    mother = parents.get("mother")
    if not father and not mother:
        return ""
    if person_pron["subj"] == "she":
        relation = "Daughter"
    elif person_pron["subj"] == "he":
        relation = "Son"
    else:
        relation = "Child"
    if father and mother:
        return f"{relation} of {father} and {mother}."
    if father:
        return f"{relation} of {father}."
    return f"{relation} of {mother}."


def _age_phrase_at_marriage(birth: Optional[str], event_date: Optional[str], event_year: Optional[int],
                            pron: Dict[str, str], approx: bool) -> Optional[str]:
    birth_year = _extract_year(birth) if birth else None
    if not birth_year or not event_year:
        return None
    if not approx and birth and event_date:
        bdt = _parse_iso_date(birth)
        edt = _parse_iso_date(event_date)
        if bdt and edt:
            age = calc_age_exact(bdt, edt)
            return f"{pron['subj']} was {format_age_exact(age)}"
    age = calc_age_approx(birth_year, event_year)
    return f"{pron['subj']} was {format_age_approx(age)}"


def _format_spouses_block(person: dict, person_pron: Dict[str, str]) -> str:
    spouses = person.get("spouses") or []
    children = person.get("children") or []
    if not spouses:
        if not children:
            return "No records of marriage or children have been found to date."
        return "No records of marriage have been found to date."

    def marriage_sort_key(sp: dict) -> int:
        m = sp.get("marriage", {})
        date_str = m.get("date")
        approx = m.get("approx")
        year = _extract_year(date_str) or _extract_year(approx) or 9999
        return year

    spouses_sorted = sorted(spouses, key=marriage_sort_key)
    pieces: List[str] = []
    for idx, sp in enumerate(spouses_sorted, start=1):
        sp_pron = _pronouns(sp.get("gender"))
        ord_word = _ordinal(idx)
        birth = sp.get("birth", {})
        bdate = birth.get("date")
        bplace = birth.get("place")

        text = f"{person_pron['poss'].capitalize()} {ord_word} spouse was {sp['name']}"
        if bdate or bplace:
            birth_bits: List[str] = []
            if bdate:
                dt = _parse_iso_date(bdate)
                if dt:
                    birth_bits.append(f"on {format_date_long(bdate)}")
                else:
                    year = _extract_year(bdate)
                    if year:
                        birth_bits.append(f"in {year}")
            if bplace:
                if birth_bits:
                    birth_bits.append(f" in {bplace}")
                else:
                    birth_bits.append(f"in {bplace}")
            text += ", who was born " + "".join(birth_bits)
        text += "."

        marriage = sp.get("marriage", {})
        date_phrase, m_year = _describe_date(marriage.get("date"), marriage.get("approx"))
        if date_phrase:
            approx_flag = not bool(_parse_iso_date(marriage.get("date")))
            text += f" They were married {date_phrase}"
            age_phrases: List[str] = []
            sp_age = _age_phrase_at_marriage(bdate, marriage.get("date"), m_year, sp_pron, approx_flag)
            if sp_age:
                age_phrases.append(sp_age)
            pers_age = _age_phrase_at_marriage(person.get("birth", {}).get("date"), marriage.get("date"),
                                               m_year, person_pron, approx_flag)
            if pers_age:
                age_phrases.append(pers_age)
            if age_phrases:
                text += "; " + " and ".join(age_phrases)
            text += "."
        else:
            text += " No record of the marriage date has been found."

        if sp.get("children_estimate"):
            text += f" Together they had at least {sp['children_estimate']} children."

        pieces.append(text)

    if not children and not any(sp.get("children_estimate") for sp in spouses_sorted):
        pieces.append("No records of children have been found to date.")

    return " ".join(pieces)


def _age_phrase_at_death(birth: Optional[str], death: Optional[str], approx: bool) -> Optional[str]:
    birth_year = _extract_year(birth) if birth else None
    death_year = _extract_year(death) if death else None
    if not birth_year or not death_year:
        return None
    bdt = _parse_iso_date(birth) if birth else None
    ddt = _parse_iso_date(death) if death else None
    if not approx and bdt and ddt:
        age = calc_age_exact(bdt, ddt)
        return f"at the age of {format_age_exact(age)}"
    age = calc_age_approx(birth_year, death_year)
    return f"at approximately {age} years of age"


def _format_deaths_block(person: dict, person_pron: Dict[str, str]) -> str:
    events: List[Tuple[int, str]] = []

    # Collect spouse deaths
    for sp in person.get("spouses") or []:
        death = sp.get("death")
        if not death or not death.get("date"):
            continue
        year = _extract_year(death.get("date"))
        phrase, _ = _describe_date(death.get("date"), None)
        if not phrase or not year:
            continue
        sp_pron = _pronouns(sp.get("gender"))
        birth = sp.get("birth", {}).get("date")
        age_phrase = _age_phrase_at_death(birth, death.get("date"), not bool(_parse_iso_date(death.get("date"))))
        death_sentence = f"{sp['name']} died {phrase}"
        place = death.get("place")
        if place:
            death_sentence += f" in {place}"
        if age_phrase:
            death_sentence += f", {age_phrase}"
        death_sentence += "."
        burial = sp.get("burial", {})
        bplace = burial.get("place")
        if bplace and bplace != place:
            death_sentence += f" {sp_pron['subj'].capitalize()} was buried in {bplace}."
        events.append((year, death_sentence))

    # Person's own death
    death = person.get("death")
    if death and death.get("date"):
        year = _extract_year(death.get("date"))
        phrase, _ = _describe_date(death.get("date"), None)
        approx = not bool(_parse_iso_date(death.get("date")))
        birth = person.get("birth", {}).get("date")
        age_phrase = _age_phrase_at_death(birth, death.get("date"), approx)
        death_sentence = f"{person['name']} died {phrase}"
        place = death.get("place")
        if place:
            death_sentence += f" in {place}"
        if age_phrase:
            death_sentence += f", {age_phrase}"
        death_sentence += "."
        burial = person.get("burial", {})
        bplace = burial.get("place")
        if bplace and bplace != place:
            death_sentence += f" {person_pron['subj'].capitalize()} was buried in {bplace}."
        events.append((year if year else 9999, death_sentence))
    else:
        events.append((9999, "No record of death has been found."))

    events.sort(key=lambda x: x[0])
    return " ".join(sentence for _, sentence in events)


def _format_children_list(children: Iterable[dict]) -> str:
    if not children:
        return ""
    lines = [f"\t{ch['henry_number']} {ch['name']}" for ch in children]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_biography(person: dict) -> str:
    """Return the formatted biography for ``person``."""
    person_pron = _pronouns(person.get("gender"))
    header = f"{person['henry_number']} {person['name']}"

    parts = [
        _format_birth_block(person, person_pron),
        _format_parents_block(person, person_pron),
        _format_spouses_block(person, person_pron),
        _format_deaths_block(person, person_pron),
    ]
    paragraph = " ".join(filter(None, parts))

    children_text = _format_children_list(person.get("children"))
    if children_text:
        return f"{header}\n{paragraph}\n\n{children_text}"
    return f"{header}\n{paragraph}"


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys, pathlib

    # Uso:
    # python bio_writer.py person.json   -> imprime 1 biografia
    # python bio_writer.py people.json   -> imprime várias (lista de pessoas)
    # python bio_writer.py               -> tenta abrir "person.json" no diretório atual

    path = sys.argv[1] if len(sys.argv) > 1 else "person.json"
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

    def emit(obj):
        print(build_biography(obj))
        print("\n" + "-" * 80 + "\n")

    if isinstance(data, list):
        for obj in data:
            emit(obj)
    else:
        emit(data)
