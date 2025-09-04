"""Utilities to build brief genealogy biographies following a strict format.

Public API:
    - build_biography(person: dict) -> str
    - Suporta datas ISO parciais: YYYY, YYYY-MM, YYYY-MM-DD.

Notes
-----
- Apenas biblioteca padrão do Python.
- Datas esperadas em ISO YYYY-MM-DD (ou parciais YYYY-MM / YYYY). Se inválidas, são ignoradas.
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
# Date parsing/formatting helpers (aceitam YYYY | YYYY-MM | YYYY-MM-DD)
# ---------------------------------------------------------------------------

def _parse_ymd(s: str | None) -> date | None:
    """Retorna date apenas se for YYYY-MM-DD válido (usado para cálculos de idade)."""
    if not s:
        return None
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except Exception:
        return None

def _parse_partial(s: str | None) -> tuple[int | None, int | None, int | None]:
    """Retorna (year, month, day), aceitando YYYY, YYYY-MM, YYYY-MM-DD."""
    if not s:
        return (None, None, None)
    parts = s.split("-")
    try:
        y = int(parts[0])
        m = int(parts[1]) if len(parts) >= 2 else None
        d = int(parts[2]) if len(parts) == 3 else None
        return (y, m, d)
    except Exception:
        return (None, None, None)

def _format_when_iso(s: str | None) -> str | None:
    """Formata:
       - 'YYYY-MM-DD' → '9 March 1900'
       - 'YYYY-MM'    → 'March 1900'
       - 'YYYY'       → '1900'
    """
    y, m, d = _parse_partial(s)
    if not y:
        return None
    if m and d:
        try:
            return f"{d} {_MONTHS_EN[m]} {y}"
        except Exception:
            return f"{y}"
    if m:
        return f"{_MONTHS_EN[m]} {y}"
    return f"{y}"

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

def _format_date(d: date) -> str:
    return f"{d.day} {_MONTHS_EN[d.month]} {d.year}"

def _has_death_info(entry: dict | None) -> bool:
    d = (entry or {}).get("death") or {}
    return bool(d.get("date") or d.get("place"))

def _age_on_exact(d_birth: date | None, d_event: date | None) -> int | None:
    if not d_birth or not d_event:
        return None
    years = d_event.year - d_birth.year
    if (d_event.month, d_event.day) < (d_birth.month, d_birth.day):
        years -= 1
    return years

def _age_on_partial(birth_iso: str | None, event_iso: str | None) -> tuple[int | None, bool]:
    """
    Retorna (idade, approx) usando datas possivelmente parciais (YYYY | YYYY-MM | YYYY-MM-DD).
    approx=True quando qualquer uma das datas for parcial (sem dia, ou sem mês).
    """
    by, bm, bd = _parse_partial(birth_iso)
    ey, em, ed = _parse_partial(event_iso)
    if not by or not ey:
        return (None, False)

    # Se ambas completas, delega ao cálculo exato.
    db = _parse_ymd(birth_iso)
    de = _parse_ymd(event_iso)
    if db and de:
        return (_age_on_exact(db, de), False)

    # Cálculo aproximado (pelo menos um lado é parcial)
    age = ey - by

    # Se temos mês de ambos, podemos ajustar um pouco melhor:
    if bm and em:
        # Sem dias confiáveis → aproximação
        # Se o evento ocorreu antes do mês de nascimento, diminui 1
        if em < bm:
            age -= 1
        # Se mesmo mês mas sem dia/ordem clara, permanece como "about"
    # Caso contrário, mantemos a diferença de anos simples

    return (age, True)

_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
}

def _ordinal(n: int) -> str:
    """Converte número em ordinal em inglês (1 -> first, etc.)."""
    return _ORDINALS.get(n, f"{n}th")

def _norm_place(s: str | None) -> str:
    """Normaliza lugares para comparação (casefold + trim)."""
    return (s or "").strip().casefold()

def _indent_from_henry(hn: str) -> str:
    """Número de tabs = quantidade de pontos no Henry (1 → 0 tabs; 1.1 → 1; 1.1.1 → 2...)."""
    return "\t" * (hn.count("."))

import re

def _last_token(s: str | None) -> str:
    """Última palavra (sobrenome) em 'Nome Sobrenome'."""
    if not isinstance(s, str):
        return ""
    parts = [p for p in s.strip().split() if p and p.strip("—-")]
    return (parts[-1] if parts else "").strip(",. ")

def _infer_children_for_spouse(person: dict, spouse: dict) -> int:
    """
    Retorna quantos filhos foram desse casamento.
    Prioridade:
      1) spouse['children_count'] (ou 'children')
      2) Heurística de sobrenome (Kennedy, Cook, etc.) nos filhos de `person`.
    """
    # 1) Preferência por contagem explícita no cônjuge
    if isinstance(spouse.get("children_count"), int):
        return spouse["children_count"]
    if isinstance(spouse.get("children"), list) and spouse["children"]:
        return len(spouse["children"])

    # 2) Heurística por sobrenome
    spouse_surname = _last_token(spouse.get("name"))
    if not spouse_surname:
        return 0

    cnt = 0
    for ch in (person.get("children") or []):
        nm = (ch or {}).get("name") or ""
        child_surname = _last_token(nm)
        if child_surname and spouse_surname.lower() == child_surname.lower():
            cnt += 1
    return cnt


# ---------------------------------------------------------------------------
# Configurações globais
# ---------------------------------------------------------------------------

# Considera "falecido" se idade estimada >= este valor e não houver óbito registrado
AGE_ASSUME_DECEASED_YEARS = 100

def _is_likely_deceased(person: dict) -> bool:
    """Retorna True se a pessoa tem óbito registrado OU se idade estimada >= limiar."""
    if _has_death_info(person):
        return True

    d_b = _parse_ymd((person.get("birth") or {}).get("date"))
    if d_b:
        today = date.today()
        age = _age_on_exact(d_b, today)
        if age is not None and age >= AGE_ASSUME_DECEASED_YEARS:
            return True

    return False


def _children_intro(person: dict, P: Dict[str, str]) -> str:
    verb = "were" if _is_likely_deceased(person) else "are"
    return f"{P['poss'].capitalize()} children {verb}:"

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
    when = _format_when_iso(birth.get("date"))
    place = birth.get("place")

    sentence = f"{_safe_name(person)} was born"
    if when and place:
        sentence += f" on {when}, in {place}"
    elif when:
        sentence += f" on {when}"
    elif place:
        sentence += f" in {place}"
    sentence += "."

    # --- pais ---
    parents = person.get("parents") or {}
    father = (
        parents.get("father") or
        parents.get("father_name") or
        person.get("father") or
        person.get("father_name")
    )
    mother = (
        parents.get("mother") or
        parents.get("mother_name") or
        person.get("mother") or
        person.get("mother_name")
    )

    if father or mother:
        # vivo ou falecido?
        alive = not bool(person.get("death"))
        verb = "is" if alive else "was"

        relation = "son" if P["subj"] == "He" else ("daughter" if P["subj"] == "She" else "child")
        if father and mother:
            parents_phrase = f"{verb} the {relation} of {father} and {mother}."
        elif father:
            parents_phrase = f"{verb} the {relation} of {father}."
        else:
            parents_phrase = f"{verb} the {relation} of {mother}."

        sentence += f" {P['subj']} {parents_phrase}"

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
    marriage = spouse.get("marriage")
    if marriage is None:
        return ""

    m = marriage or {}
    d_m = _parse_ymd(m.get("date"))  # só calcula idade se for data completa
    when = _format_when_iso(m.get("date")) or ""
    d_pb = _parse_ymd((person.get("birth") or {}).get("date"))
    d_sb = _parse_ymd((spouse.get("birth") or {}).get("date"))

    place = m.get("place")

    parts: List[str] = []
    if when and place:
        parts.append(f"They were married on {when} in {place}")
    elif when:
        parts.append(f"They were married on {when}")
    elif place:
        parts.append(f"They were married in {place}")

    a_p, approx_p = _age_on_partial((person.get("birth") or {}).get("date"), (marriage or {}).get("date"))
    a_s, approx_s = _age_on_partial((spouse.get("birth") or {}).get("date"), (marriage or {}).get("date"))

    if a_p is not None and a_s is not None and parts:
        if a_p is not None and a_s is not None and parts:
            about = " about" if (approx_p or approx_s) else ""
            parts[-1] += f"; {P['subj'].lower()} was{about} {a_p} and {S['subj'].lower()} was{about} {a_s}."
        elif parts:
            parts[-1] += "."

    return " ".join(parts).strip()

def _children_clause(person: dict, spouse: dict) -> str:
    # Preferência por dados do cônjuge; se ausentes, usa heurística de sobrenome.
    n = _infer_children_for_spouse(person, spouse)

    if n > 0:
        return f"From this marriage, they had at least {n} children."
    else:
        person_children = person.get("children") or []
        if person_children:
            return "From this marriage, no specific records link children to this union."
        return "No records of children have been found to date."



def _death_sentence(person: dict, P: Dict[str, str]) -> Optional[str]:
    birth = person.get("birth") or {}
    b_place = birth.get("place")

    death = person.get("death") or {}
    d_d = _parse_ymd(death.get("date"))  # para cálculo de idade, se houver dia
    when = _format_when_iso(death.get("date"))
    d_place = death.get("place")

    age, approx_age = _age_on_partial(birth.get("date"), (death or {}).get("date"))

    if not when and not d_place:
        return None

    core = f"{_safe_name(person)} died"
    if when and d_place:
        core += f" on {when} in {d_place}"
    elif when:
        core += f" on {when}"
    else:
        core += f" in {d_place}"

    if age is not None:
        core += f", at the age of{' about' if approx_age else ''} {age}."
    else:
        core += "."

    burial_place = (person.get("burial") or {}).get("place")

    # Evita redundância:
    # 1) Se sepultamento = local do óbito → já era coberto antes (não repetir).
    # 2) Se sepultamento = local de nascimento → não repetir.
    if burial_place:
        same_as_death = _norm_place(burial_place) == _norm_place(d_place)
        same_as_birth = _norm_place(burial_place) == _norm_place(b_place)
        if not same_as_death and not same_as_birth:
            core += f" {P['subj']} was buried in {burial_place}."

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
    """Henry list: uma por linha, indentação por nível (tabs), formato '<henry> <nome>'."""
    lines = []
    for ch in (children or []):
        hn = (ch or {}).get("henry_number") or ""
        nm = _safe_name(ch, "")
        if hn and nm:
            lines.append(f"{_indent_from_henry(hn)}{hn} {nm}")
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

    indent_level = henry.count(".")  # cada ponto = um nível
    indent = "\t" * indent_level  # usa tabulação para deslocar
    header = f"{indent}{henry} {name}"

    parts: List[str] = []
    parts.append(_format_birth_parents(person, P))

    spouses = person.get("spouses") or []
    children = person.get("children") or []

    # Flag para evitar duplicar a frase de ausência total
    added_unified_absence = False

    # Caso sem casamento e sem filhos (regra Shepard #6)
    if not spouses and not children:
        # Se também não há óbito registrado → frase unificada
        if not _has_death_info(person):
            parts.append("No records of marriage, children or death have been found to date.")
            added_unified_absence = True
        else:
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
            parts.append(_children_clause(person, sp or {}))

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
        else:
            # Pessoa sem cônjuge e sem registro de óbito
            if not _has_death_info(person) and not added_unified_absence:
                parts.append("No records of death have been found to date.")

    # Lista Henry de filhos (tabulada), após a biografia
    children_block = _format_children_list(children)

    # Monta o corpo principal (sem a parte dos filhos)
    main_text = " ".join(s.strip() for s in parts if s and s.strip())

    if children_block:
        body = f"{main_text}\n\n\tTheir children were:\n\n{children_block}"
    else:
        body = main_text

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
