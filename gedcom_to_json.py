# gedcom_to_json.py
# Lê pessoas via ged4py, e RELACIONAMENTOS (pais/cônjuges/filhos) via scanner de texto do GED
from __future__ import annotations
from ged4py.parser import GedcomReader
import json, re, sys, os, tempfile, traceback
from pathlib import Path

# -------------------- Utils --------------------
def _val_to_str(node):
    if not node: return None
    v = getattr(node, "value", None)
    return None if v is None else str(v)

def _clean_id(x):
    return None if x is None else str(x).strip()

# -------------------- Scanner simples de FAM no arquivo .GED --------------------
FAM_START_RE = re.compile(r"^0\s+(@F\d+@)\s+FAM\s*$", re.IGNORECASE)
HUSB_RE      = re.compile(r"^\s*1\s+HUSB\s+(@I\d+@)\s*$", re.IGNORECASE)
WIFE_RE      = re.compile(r"^\s*1\s+WIFE\s+(@I\d+@)\s*$", re.IGNORECASE)
CHIL_RE      = re.compile(r"^\s*1\s+CHIL\s+(@I\d+@)\s*$", re.IGNORECASE)
MARR_START   = re.compile(r"^\s*1\s+MARR\s*$", re.IGNORECASE)
DATE_RE      = re.compile(r"^\s*2\s+DATE\s+(.+?)\s*$", re.IGNORECASE)
PLAC_RE      = re.compile(r"^\s*2\s+PLAC\s+(.+?)\s*$", re.IGNORECASE)

def parse_families_raw(ged_path: str) -> dict[str, dict]:
    """
    Varre o .ged como texto e monta um dicionário:
      families[fid] = {
        "husband": "@I..@" | None,
        "wife": "@I..@" | None,
        "children": ["@I..@", ...],
        "marriage": {"date": "...", "place": "..."} (se houver)
      }
    """
    families: dict[str, dict] = {}
    current_fid = None
    inside_marr = False
    marr_obj = None

    with open(ged_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            # Novo bloco de família
            m = FAM_START_RE.match(line)
            if m:
                current_fid = _clean_id(m.group(1))
                families[current_fid] = {"husband": None, "wife": None, "children": []}
                inside_marr = False
                marr_obj = None
                continue

            if current_fid is None:
                continue  # ainda não estamos dentro de um bloco FAM

            # Dentro do bloco FAM atual:
            m = HUSB_RE.match(line)
            if m:
                families[current_fid]["husband"] = _clean_id(m.group(1))
                continue

            m = WIFE_RE.match(line)
            if m:
                families[current_fid]["wife"] = _clean_id(m.group(1))
                continue

            m = CHIL_RE.match(line)
            if m:
                cid = _clean_id(m.group(1))
                if cid: families[current_fid]["children"].append(cid)
                continue

            # Casamento: 1 MARR  →  2 DATE / 2 PLAC logo abaixo
            if MARR_START.match(line):
                inside_marr = True
                marr_obj = {}
                continue

            if inside_marr:
                dm = DATE_RE.match(line)
                if dm:
                    marr_obj["date"] = dm.group(1).strip()
                    families[current_fid]["marriage"] = marr_obj
                    continue
                pm = PLAC_RE.match(line)
                if pm:
                    marr_obj["place"] = pm.group(1).strip()
                    families[current_fid]["marriage"] = marr_obj
                    continue
                # se veio outro nível 1, encerra MARR
                if re.match(r"^\s*1\s+\S+", line):
                    inside_marr = False
                    marr_obj = None

    return families

# -------------------- Parser principal --------------------
def parse_gedcom(file_path: str) -> list[dict]:
    people: dict[str, dict] = {}
    famc_map: dict[str, list[str]] = {}
    fams_map: dict[str, list[str]] = {}

    indi_count = 0
    indi_errors = 0

    print(f"[INFO] Abrindo GEDCOM: {file_path}")

    # 1) Pessoas (via ged4py)
    with GedcomReader(file_path) as parser:
        for indi in parser.records0("INDI"):
            indi_count += 1
            try:
                pid = _clean_id(indi.xref_id)
                person = {
                    "id": pid,
                    "name": indi.name.format() if getattr(indi, "name", None) else None,
                    "sex": getattr(indi, "sex", None),
                }

                # nascimento
                birth = indi.sub_tag("BIRT")
                if birth:
                    b = {}
                    dval = _val_to_str(birth.sub_tag("DATE"))
                    pval = _val_to_str(birth.sub_tag("PLAC"))
                    if dval is not None: b["date"] = dval
                    if pval is not None: b["place"] = pval
                    if b: person["birth"] = b

                # óbito
                death = indi.sub_tag("DEAT")
                if death:
                    d = {}
                    dval = _val_to_str(death.sub_tag("DATE"))
                    pval = _val_to_str(death.sub_tag("PLAC"))
                    if dval is not None: d["date"] = dval
                    if pval is not None: d["place"] = pval
                    if d: person["death"] = d

                # ponteiros de família (se o ged4py der, ótimo; se não, seguimos com CHIL do scanner)
                for famc in indi.sub_tags("FAMC"):
                    fid = _clean_id(famc.value)
                    if fid: famc_map.setdefault(pid, []).append(fid)
                for fams in indi.sub_tags("FAMS"):
                    fid = _clean_id(fams.value)
                    if fid: fams_map.setdefault(pid, []).append(fid)

                people[pid] = person
            except Exception as e:
                indi_errors += 1
                print(f"[WARN] Erro INDI {indi_count}: {e}")
                traceback.print_exc(limit=1)

    print(f"[INFO] INDI lidos: {indi_count} (erros: {indi_errors})")

    # 2) Famílias (via scanner de texto, confiável)
    families = parse_families_raw(file_path)
    print(f"[INFO] FAM lidas (scanner): {len(families)}")

    # 3) Relacionamentos usando families do scanner
    with_parents = with_spouses = with_children = 0

    # 3.A) Via FAM (HUSB/WIFE/CHIL) — sempre funciona pelo scanner
    for fid, fam in families.items():
        husb = _clean_id(fam.get("husband"))
        wife = _clean_id(fam.get("wife"))
        kids = [ _clean_id(c) for c in fam.get("children", []) ]

        # spouses
        if husb and (husb in people) and wife and (wife in people):
            sp = {
                "partner_id": wife,
                "name": people[wife]["name"],
                "sex": people[wife].get("sex", "F"),
                "children_count": len([k for k in kids if k in people]),
            }
            if "marriage" in fam:
                sp["marriage"] = fam["marriage"]
            people[husb].setdefault("spouses", []).append(sp)
        if wife and (wife in people) and husb and (husb in people):
            sp = {
                "partner_id": husb,
                "name": people[husb]["name"],
                "sex": people[husb].get("sex", "M"),
                "children_count": len([k for k in kids if k in people]),
            }
            if "marriage" in fam:
                sp["marriage"] = fam["marriage"]
            people[wife].setdefault("spouses", []).append(sp)

        # children + parents
        for c in kids:
            if c and (c in people):
                child_ref = {"id": c, "name": people[c]["name"]}
                if husb and (husb in people):
                    people[husb].setdefault("children", []).append(child_ref)
                if wife and (wife in people):
                    people[wife].setdefault("children", []).append(child_ref)

                father_id = husb if (husb and husb in people) else None
                mother_id = wife if (wife and wife in people) else None
                if father_id or mother_id:
                    people[c]["parents"] = {
                        "father_name": people[father_id]["name"] if father_id else None,
                        "mother_name": people[mother_id]["name"] if mother_id else None,
                    }
                    people[c]["parents_ids"] = {
                        "father_id": father_id,
                        "mother_id": mother_id,
                    }

    # Contadores finais
    with_parents  = sum(1 for p in people.values() if "parents" in p or "parents_ids" in p)
    with_spouses  = sum(1 for p in people.values() if "spouses" in p)
    with_children = sum(1 for p in people.values() if "children" in p)

    print(f"[CHECK] pessoas com parents:  {with_parents}")
    print(f"[CHECK] pessoas com spouses:  {with_spouses}")
    print(f"[CHECK] pessoas com children: {with_children}")

    if "@I1@" in people:
        print("[CHECK] Wayne (@I1@):")
        print("        parents     =", people["@I1@"].get("parents"))
        print("        parents_ids =", people["@I1@"].get("parents_ids"))
        print("        spouses     =", people["@I1@"].get("spouses"))
        print("        children    =", people["@I1@"].get("children"))

    return list(people.values())

# -------------------- Escrita segura --------------------
def write_atomic_json(data, out_path: Path):
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(out_path.parent), suffix=".tmp") as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_name = tmp.name
    os.replace(tmp_name, out_path)

# -------------------- Main --------------------
def main():
    in_name = "shepard_family.ged"
    out_name = "saida.json"
    if len(sys.argv) >= 2: in_name = sys.argv[1]
    if len(sys.argv) >= 3: out_name = sys.argv[2]

    project_dir = Path(__file__).parent.resolve()
    in_path = (project_dir / in_name) if not Path(in_name).is_absolute() else Path(in_name)
    out_path = (project_dir / out_name) if not Path(out_name).is_absolute() else Path(out_name)

    if not in_path.exists():
        print(f"[ERRO] GEDCOM não encontrado: {in_path}")
        sys.exit(1)

    people = parse_gedcom(str(in_path))
    print(f"[INFO] Pessoas coletadas: {len(people)}")
    print(f"[INFO] Gravando JSON em: {out_path}")
    write_atomic_json(people, out_path)
    print(f"[OK] Convertido {len(people)} indivíduos para {out_path}")

if __name__ == "__main__":
    main()
