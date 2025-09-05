# bio_writer.py — gera biografias no padrão Shepard a partir de saida.json
import json
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).parent.resolve()
JSON_PATH = PROJECT_DIR / "saida.json"
OUT_DIR = PROJECT_DIR / "bios"

def fmt_date(d):
    """Converte o dicionário de data (ou string) em texto amigável."""
    if not d:
        return None
    if isinstance(d, str):
        return d
    # d pode vir como {"date": "...", "year": 1965, "month": 2, "day": 10, "qualifier": "...", "place": "..."}
    return d.get("date") or None

def line_if(prefix, value):
    return f"{prefix}{value}\n" if value else ""

def build_bio(person, people_index):
    name = person.get("name") or "—"
    sex = person.get("sex") or "—"

    # nascimento / falecimento
    birth = person.get("birth", {})
    death = person.get("death", {})

    birth_date = fmt_date(birth)
    birth_place = birth.get("place") if isinstance(birth, dict) else None
    death_date = fmt_date(death)
    death_place = death.get("place") if isinstance(death, dict) else None

    # pais
    parents = person.get("parents", {})
    father_name = parents.get("father_name")
    mother_name = parents.get("mother_name")

    # cônjuges
    spouses = person.get("spouses", [])
    # filhos
    children = person.get("children", [])

    # ----- TEXTO PADRÃO SHEPARD -----
    # Ajuste aqui o “molde” se quiser mudar o estilo.
    lines = []
    lines.append(f"# {name}\n")
    lines.append(line_if("Sexo: ", "Masculino" if sex == "M" else ("Feminino" if sex == "F" else sex)))
    lines.append(line_if("Nascimento: ", f"{birth_date}" + (f" — {birth_place}" if birth_place else "")))
    lines.append(line_if("Falecimento: ", f"{death_date}" + (f" — {death_place}" if death_place else "")))

    # pais
    if father_name or mother_name:
        pai_mae = []
        if father_name: pai_mae.append(f"pai **{father_name}**")
        if mother_name: pai_mae.append(f"mãe **{mother_name}**")
        lines.append(f"Filho(a) de " + " e ".join(pai_mae) + ".\n")

    # cônjuges
    if spouses:
        lines.append("## Cônjuges")
        for sp in spouses:
            sp_name = sp.get("name") or "—"
            marr = sp.get("marriage", {})
            marr_date = fmt_date(marr)
            marr_place = marr.get("place") if isinstance(marr, dict) else None
            cc = sp.get("children_count", 0)
            part_line = f"- **{sp_name}**"
            if marr_date or marr_place:
                detalhe = " — casamento"
                if marr_date: detalhe += f" em {marr_date}"
                if marr_place: detalhe += f", {marr_place}"
                part_line += detalhe
            part_line += f" (filhos: {cc})"
            lines.append(part_line)
        lines.append("")

    # filhos
    if children:
        lines.append("## Filhos")
        for ch in children:
            cid = ch.get("id")
            cname = ch.get("name")
            # enriquece com datas se existir no índice
            if cid and cid in people_index:
                cbirth = people_index[cid].get("birth", {})
                cdate = fmt_date(cbirth)
                cplace = cbirth.get("place") if isinstance(cbirth, dict) else None
                extra = ""
                if cdate: extra += f" — {cdate}"
                if cplace: extra += f" — {cplace}"
                lines.append(f"- {cname}{extra}")
            else:
                lines.append(f"- {cname}")
        lines.append("")

    # separador opcional
    return "\n".join(l for l in lines if l is not None)

def main():
    # permite passar um nome/trecho pra gerar apenas 1 bio:
    #   python bio_writer.py "Wayne"
    name_filter = " ".join(sys.argv[1:]).strip().lower() if len(sys.argv) > 1 else None

    if not JSON_PATH.exists():
        print(f"[ERRO] Não encontrei {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        people = json.load(f)

    # índice por id
    people_index = {p.get("id"): p for p in people if p.get("id")}

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for p in people:
        pname = p.get("name") or ""
        # filtro por nome se passado
        if name_filter and name_filter not in pname.lower():
            continue

        # nome do arquivo: "I1 - Wayne Lee Elsey.md"
        pid = (p.get("id") or "").strip("@")
        safe_name = "".join(ch for ch in pname if ch.isalnum() or ch in " .-_").strip()
        out_file = OUT_DIR / f"{pid} - {safe_name}.md"

        bio = build_bio(p, people_index)
        out_file.write_text(bio, encoding="utf-8")
        total += 1

    if name_filter:
        print(f"[OK] Geradas {total} biografia(s) filtradas por: {name_filter!r} → {OUT_DIR}")
    else:
        print(f"[OK] Geradas {total} biografias em: {OUT_DIR}")

if __name__ == "__main__":
    main()
