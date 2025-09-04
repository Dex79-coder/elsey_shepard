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

def _collect_spouse_children_hn(sp: dict) -> set[str]:
    vals = sp.get("children_henry_numbers")
    if isinstance(vals, list):
        return {str(x).strip() for x in vals if str(x).strip()}
    return set()

def _children_distribution(person: dict) -> dict:
    """
    Retorna um dict com:
      - marriages_count: int
      - total_children: int
      - per_spouse: list de {index, spouse_name, count, source}
      - outside_count: int | None (None = não declarado)
    Prioridade: children_henry_numbers > children_count > spouse.children > (indeterminado)
    """
    spouses = person.get("spouses") or []
    children = person.get("children") or []
    total_children = len(children)

    per = []
    used_hn = set()  # evita duplo-contar se vierem listas por cônjuge
    for idx, sp in enumerate(spouses, start=1):
        name = (sp or {}).get("name") or f"Spouse {idx}"
        hn_set = _collect_spouse_children_hn(sp or {})
        if hn_set:
            per.append({"index": idx, "spouse_name": name, "count": len(hn_set), "source": "declared_list"})
            used_hn |= hn_set
            continue

        if isinstance(sp.get("children_count"), int):
            per.append({"index": idx, "spouse_name": name, "count": sp["children_count"], "source": "declared_count"})
            continue

        if isinstance(sp.get("children"), list):
            per.append({"index": idx, "spouse_name": name, "count": len(sp["children"]), "source": "spouse_children_list"})
            continue

        per.append({"index": idx, "spouse_name": name, "count": 0, "source": "unknown"})

    # Fora do casamento (apenas se declarado)
    outside_decl = person.get("outside_children_henry_numbers")
    if isinstance(outside_decl, list) and outside_decl:
        outside_count = len({str(x).strip() for x in outside_decl if str(x).strip()})
    else:
        outside_count = None  # não afirmar sem registro explícito

    return {
        "marriages_count": len(spouses),
        "total_children": total_children,
        "per_spouse": per,
        "outside_count": outside_count,
    }

def _format_qna_pt(person: dict, dist: dict) -> str:
    """
    Gera bloco-resumo em PT, seguindo seu roteiro:
    - Quantos casamentos teve?
    - Teve filhos?
    - Foi fora do casamento?
    - Qual? (distribuição por casamento)
    - Quantos por casamento e fora do casamento (se declarado)
    """
    indent_base = "\t" * ((person.get("henry_number") or "").count(".") + 1)

    marriages = dist["marriages_count"]
    total_children = dist["total_children"]
    per = dist["per_spouse"]
    outside = dist["outside_count"]  # None = não declarado

    lines = []
    lines.append(f"{indent_base}Quantos casamentos teve? {'Nenhum' if marriages == 0 else marriages}")
    lines.append(f"{indent_base}Teve filhos? {'Sim' if total_children > 0 else 'Não (sem registros de filhos encontrados)'}")

    # Fora do casamento
    if outside is None:
        # Sem registro explícito, evitar afirmação
        lines.append(f"{indent_base}Foi fora do casamento? Não há registros que indiquem filhos fora do casamento.")
    else:
        lines.append(f"{indent_base}Foi fora do casamento? {'Sim' if outside > 0 else 'Não'}")

    # Distribuição por casamento
    if marriages > 0:
        lines.append(f"{indent_base}Distribuição por casamento:")
        for item in per:
            idx = item["index"]
            cnt = item["count"]
            lines.append(f"{indent_base}- {idx}º casamento: {cnt}")
        if outside is not None:
            lines.append(f"{indent_base}- Fora do casamento: {outside}")

    return "\n".join(lines)


import re

def _last_token(s: str | None) -> str:
    if not isinstance(s, str):
        return ""
    parts = [p for p in s.strip().split() if p and p.strip("—-")]
    return (parts[-1] if parts else "").strip(",. ").casefold()

def _soundex_key(token: str) -> str:
    """Soundex simples (suficiente p/ Muncey/Muncy/Muncie/Munsey)."""
    if not token:
        return ""
    t = re.sub(r'[^A-Za-z]', '', token).upper()
    if not t:
        return ""
    # 1) primeira letra
    first = t[0]
    # 2) mapa
    table = str.maketrans({
        **{c:"1" for c in "BFPV"},
        **{c:"2" for c in "CGJKQSXZ"},
        **{c:"3" for c in "DT"},
        **{c:"4" for c in "L"},
        **{c:"5" for c in "MN"},
        **{c:"6" for c in "R"},
    })
    # 3) codificar resto
    coded = t[1:].translate(table)
    # 4) remover vogais/Y/H/W (viram 0 na prática)
    coded = re.sub(r'[AEIOUYHW]', '0', coded)
    # 5) colapsar duplicados
    coded = re.sub(r'(\d)\1+', r'\1', coded)
    # 6) remover zeros
    coded = coded.replace('0', '')
    # 7) montar/padding
    key = (first + coded + "000")[:4]
    return key

def _surname_key(s: str | None) -> str:
    return _soundex_key(_last_token(s))

def _infer_children_for_spouse(person: dict, spouse: dict) -> int:
    # 1) Dado explícito sempre vence
    if isinstance(spouse.get("children_count"), int):
        return spouse["children_count"]

    ch_nums = spouse.get("children_henry_numbers")
    if isinstance(ch_nums, list) and ch_nums:
        return len(ch_nums)

    # 2) Se o cônjuge carregou uma lista própria de filhos, usa
    if isinstance(spouse.get("children"), list) and spouse["children"]:
        return len(spouse["children"])

    # 3) Fallback: inferência fonética por sobrenome (já implementada)
    key_sp = _surname_key(spouse.get("name"))
    if not key_sp:
        return 0
    cnt = 0
    for ch in (person.get("children") or []):
        nm = (ch or {}).get("name") or ""
        if nm and _surname_key(nm) == key_sp:
            cnt += 1
    return cnt



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

# Mostrar bloco-resumo Q&A (português) ao final da biografia
ENABLE_QNA_SUMMARY_PT = False

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
    when = _format_when_iso(m.get("date")) or ""
    place = (m.get("place") or "").strip()

    # frase-base
    if when and place:
        sentence = f"They were married on {when} in {place}"
    elif when:
        sentence = f"They were married on {when}"
    elif place:
        sentence = f"They were married in {place}"
    else:
        return ""

    # idades (exatas ou "about")
    a_p, approx_p = _age_on_partial((person.get("birth") or {}).get("date"), (marriage or {}).get("date"))
    a_s, approx_s = _age_on_partial((spouse.get("birth") or {}).get("date"), (marriage or {}).get("date"))
    if a_p is not None and a_s is not None:
        about = " about" if (approx_p or approx_s) else ""
        sentence += f"; {P['subj'].lower()} was{about} {a_p} and {S['subj'].lower()} was{about} {a_s}"

    # ponto final garantido
    if not sentence.endswith("."):
        sentence += "."

    return sentence


def _children_clause(person: dict, spouse: dict) -> str:
    n = _infer_children_for_spouse(person, spouse)
    if n > 0:
        word = "child" if n == 1 else "children"
        return f"From this marriage, they had at least {n} {word}."
    return ""


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

def _is_100_plus_without_death(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if _has_death_info(entry):
        return False
    birth_iso = (entry.get("birth") or {}).get("date")
    y, m, d = _parse_partial(birth_iso)
    if not y:
        return False
    today = date.today()
    return (today.year - y) >= AGE_ASSUME_DECEASED_YEARS


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
        # Regra #7: ausência de óbitos unificada (+ 'as of <today>' quando >=100 anos)
        today_str = _format_date(date.today())
        if spouses:
            all_names = [name] + [_safe_name(sp) for sp in spouses]
            needs_asof = _is_100_plus_without_death(person) or any(
                _is_100_plus_without_death(sp or {}) for sp in spouses)
            tail = f" as of {today_str}." if needs_asof else "."
            if len(all_names) == 2:
                parts.append(f"No records of death have been found to date for {all_names[0]} and {all_names[1]}{tail}")
            else:
                parts.append(
                    "No records of death have been found to date for "
                    + ", ".join(all_names[:-1])
                    + f", and {all_names[-1]}{tail}"
                )
        else:
            if not _has_death_info(person) and not added_unified_absence:
                if _is_100_plus_without_death(person):
                    parts.append(f"No records of death have been found to date as of {today_str}.")
                else:
                    parts.append("No records of death have been found to date.")

    # Lista Henry de filhos (tabulada), após a biografia
    children_block = _format_children_list(children)

    # Monta o corpo principal (sem a parte dos filhos)
    main_text = " ".join(s.strip() for s in parts if s and s.strip())

    if children_block:
        # se houver filhos, use a identação do primeiro filho
        first_child = (children or [None])[0] or {}
        label_indent = _indent_from_henry(first_child.get("henry_number") or "")
        if not label_indent:
            # fallback: um nível abaixo do próprio henry da pessoa
            label_indent = "\t" * (henry.count(".") + 1)
        body = f"{main_text}\n\n{label_indent}Their children were:\n\n{children_block}"
    else:
        body = main_text

    # Bloco Q&A em PT (opcional)
    if ENABLE_QNA_SUMMARY_PT:
        dist = _children_distribution(person)
        qna = _format_qna_pt(person, dist)
        if qna.strip():
            body = f"{body}\n\n{qna}"

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
