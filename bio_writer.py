"""Utilities to build brief genealogy biographies following a strict format.

Public API:
    - build_biography(person: dict) -> str

Notes
-----
- Apenas biblioteca padrão do Python.
- Datas esperadas em ISO YYYY-MM-DD (ou None). Se inválidas, são ignoradas.
- Regras Shepard aplicadas:
  * Se não houver casamento e nem filhos: "No records of marriage or children have been found to date."
  * Óbitos aparecem só ao final da biografia, em ordem cronológica (mais antigo → mais recente).
  * Se não houver registros de óbito para todos (pessoa + cônjuges), usar frase unificada.
  * Lista Henry dos filhos: apenas número + nome (tabulada), após a biografia.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# English month names (avoid locale-dependent %B)
# ---------------------------------------------------------------------------
_MONTHS_EN = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pronouns(sex: str | None) -> Dict[str, str]:
    s = (sex or "").strip().upper()
    if s == "M":
        return {"subj": "He", "obj": "him", "poss": "his"}
    if s == "F":
        return {"subj": "She", "obj": "her", "poss": "her"}
    return {"subj": "They", "obj": "them", "poss": "their"}


def _parse_ymd(s: str | None) -> date | None:
    if not s:
        return None
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _format_date(d: date) -> str:
    return f"{d.day} {_MONTHS_EN[d.month]} {d.year}"


def _age_on(d_birth: date | None, d_event: date | None) -> int | None:
    if not d_birth or not d_event:
        return None
    years = d_event.year - d_birth.year
    if (d_event.month, d_event.day) < (d_birth.month, d_birth.day):
        years -= 1
    return years


_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
}


def _ordinal(n: int) -> str:
    return _ORDINALS.get(n, f"{n}th")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _safe_name(x: dict | None, fallback: str = "Unknown") -> str:
    if not isinstance(x, dict):
        return fallback
    n = x.get("name")
    return n.strip() if isinstance(n, str) and n.strip() else fallback


def _format_birth_parents(person: dict, P: Dict[str, str]) -> str:
    birth = person.get("birth") or {}
    d_b = _parse_ymd(birth.get("date"))
    when = _format_date(d_b) if d_b else None
    place = birth.get("place")

    sentence = f"{_safe_name(person)} was born"
    if when and place:
        sentence += f" on {when}, in {place}"
    elif when:
        sentence += f" on {when}"
    elif place:
        sentence += f" in {place}"

    parents = person.get("parents") or {}
    father = parents.get("father")
    mother = parents.get("mother")
    if father or mother:
        relation = "son" if P["subj"] == "He" else ("daughter" if P["subj"] == "She" else "child")
        if father and mother:
            parents_phrase = f"{relation} of {father} and {mother}"
        elif father:
            parents_phrase = f"{relation} of {father}"
        else:
            parents_phrase = f"{relation} of {mother}"
        sentence += f", {parents_phrase}"

    sentence += "."
    return sentence


def _spouse_intro(spouse: dict, P: Dict[str, str], idx: int, total: int) -> str:
    b = spouse.get("birth") or {}
    d_b = _parse_ymd(b.get("date"))
    when_b = _format_date(d_b) if d_b else None
    place_b = b.get("place")

    if total == 1:
        head = f"{P['poss'].capitalize()} spouse was {_safe_name(spouse)}"
    else:
        head = f"{P['poss'].capitalize()} {_ordinal(idx)} spouse was {_safe_name(spouse)}"

    if when_b and place_b:
        head += f", who was born on {when_b} in {place_b}."
    elif when_b:
        head += f", who was born on {when_b}."
    elif place_b:
        head += f", who was born in {place_b}."
    else:
        head += "."
    return head


def _format_marriage(person: dict, spouse: dict, P: Dict[str, str], S: Dict[str, str]) -> str:
    m = spouse.get("marriage") or {}
    d_m = _parse_ymd(m.get("date"))
    d_pb = _parse_ymd((person.get("birth") or {}).get("date"))
    d_sb = _parse_ymd((spouse.get("birth") or {}).get("date"))

    when = _format_date(d_m) if d_m else ""
    place = m.get("place")

    parts: List[str] = []
    if when and place:
        parts.append(f"They were married on {when} in {place}")
    elif when:
        parts.append(f"They were married on {when}")
    elif place:
        parts.append(f"They were married in {place}")

    a_p = _age_on(d_pb, d_m)
    a_s = _age_on(d_sb, d_m)
    if a_p is not None and a_s is not None and parts:
        parts[-1] += f"; {P['subj'].lower()} was {a_p} and {S['subj'].lower()} was {a_s}."
    elif parts:
        parts[-1] += "."

    return " ".join(parts).strip()


def _children_clause(spouse: dict) -> str:
    kids = spouse.get("children") or []
    cnt = spouse.get("children_count") or spouse.get("children_estimate")
    n = cnt if isinstance(cnt, int) else (len(kids) if kids else 0)
    if n > 0:
        return f"Together they had at least {n} children."
    return "No records of children have been found to date."


def _death_sentence(person: dict, P: Dict[str, str]) -> Optional[str]:
    b = (person.get("birth") or {}).get("date")
    d = person.get("death") or {}
    d_d = _parse_ymd(d.get("date"))
    when = _format_date(d_d) if d_d else None
    place = d.get("place")
    age = _age_on(_parse_ymd(b), d_d)

    if not when and not place:
        return None

    core = f"{_safe_name(person)} died"
    if when and place:
        core += f" on {when} in {place}"
    elif when:
        core += f" on {when}"
    else:
        core += f" in {place}"

    if age is not None:
        core += f", at the age of {age}."
    else:
        core += "."

    burial = (person.get("burial") or {}).get("place")
    if burial and (not place or burial != place):
        core += f" {P['subj']} was buried in {burial}."
    return core


def _death_tuple(entry: dict | None) -> tuple[date | None, str]:
    """Return (death_date, sentence) for later sorting."""
    if not isinstance(entry, dict):
        return (None, "")
    P = _pronouns(entry.get("gender") or entry.get("sex"))
    sent = _death_sentence(entry, P)
    d = _parse_ymd(((entry.get("death") or {}).get("date")))
    return (d, sent or "")


def _format_children_list(children: Iterable[dict]) -> str:
    """Henry list: one per line, tab-indented: '<henry> <name>'."""
    lines = []
    for ch in (children or []):
        hn = (ch or {}).get("henry_number") or ""
        nm = _safe_name(ch, "")
        if hn and nm:
            lines.append(f"\t{hn} {nm}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_biography(person: dict) -> str:
    """Build the formatted biography text for a person dict."""
    if not isinstance(person, dict):
        return ""

    name = _safe_name(person)
    henry = person.get("henry_number") or ""
    P = _pronouns(person.get("gender") or person.get("sex"))

    header = f"{henry} {name}".strip()

    parts: List[str] = []
    parts.append(_format_birth_parents(person, P))

    spouses = person.get("spouses") or []
    children = person.get("children") or []

    # Caso sem casamento e sem filhos (regra Shepard #6)
    if not spouses and not children:
        parts.append("No records of marriage or children have been found to date.")
    else:
        # Para cada cônjuge: intro, casamento e cláusula de filhos
        total = len(spouses)
        for idx, sp in enumerate(spouses, start=1):
            S = _pronouns((sp or {}).get("gender") or (sp or {}).get("sex"))
            parts.append(_spouse_intro(sp or {}, P, idx, total))
            m = _format_marriage(person, sp or {}, P, S)
            if m:
                parts.append(m)
            parts.append(_children_clause(sp or {}))

    # Óbitos (apenas no final), ordenados do mais antigo para o mais recente (regra #8)
    death_entries: List[tuple[date | None, str]] = []

    # Principal
    d_tuple = _death_tuple(person)
    if d_tuple[1]:
        death_entries.append(d_tuple)

    # Cônjuges
    for sp in spouses:
        tup = _death_tuple(sp or {})
        if tup[1]:
            death_entries.append(tup)

    # Ordena; None vai ao fim
    death_entries.sort(key=lambda x: (x[0] is None, x[0] or date.max))

    if death_entries:
        parts.append(" ".join([t for _, t in death_entries]))
    else:
        # Regra #7: ausência de óbitos unificada
        if spouses:
            all_names = [name] + [_safe_name(sp) for sp in spouses]
            if len(all_names) == 2:
                parts.append(
                    f"No records of death have been found to date for {all_names[0]} and {all_names[1]}."
                )
            else:
                parts.append(
                    "No records of death have been found to date for "
                    + ", ".join(all_names[:-1])
                    + f", and {all_names[-1]}."
                )

    # Lista Henry de filhos (tabulada), após a biografia
    children_block = _format_children_list(children)
    if children_block:
        parts.append(children_block)

    body = " ".join(s.strip() for s in parts if s and s.strip())
    return header + "\n\n" + body


__all__ = ["build_biography"]


if __name__ == "__main__":
    # Pequeno teste manual
    sample = {
        "henry_number": "1.1",
        "name": "Albert Young Shepard",
        "gender": "M",
        "birth": {"date": "1845-10-09", "place": "Rich Valley, Smyth County, Virginia, USA"},
        "parents": {"father": "William R Shepard", "mother": "Asseneth Lucinda Chenault"},
        "spouses": [
            {
                "name": "Mary Oregon Johnson",
                "gender": "F",
                "birth": {"date": "1847-03-26", "place": "Chatham Hill, Smyth County, Virginia, USA"},
                "marriage": {"date": "1865-01-22", "place": "Smyth County, Virginia, USA"},
                "children_count": 4,
                "children": [
                    {"henry_number": "1.1.1", "name": "Alice Shepard"},
                    {"henry_number": "1.1.2", "name": "Marget Matilda Shepard"},
                    {"henry_number": "1.1.3", "name": "Marinda E. Shepard"},
                    {"henry_number": "1.1.4", "name": "—"},
                ],
            }
        ],
        "death": {"date": "1945-03-16", "place": "Oakley, Cassia County, Idaho, USA"},
        "burial": {"place": "Oakley Cemetery, Oakley, Cassia County, Idaho, USA"},
        "children": [
            {"henry_number": "1.1.1", "name": "Alice Shepard"},
            {"henry_number": "1.1.2", "name": "Marget Matilda Shepard"},
            {"henry_number": "1.1.3", "name": "Marinda E. Shepard"},
            {"henry_number": "1.1.4", "name": ""},
        ],
    }
    print(build_biography(sample))
