# main.py (adições de debug + escrita atômica)
import json
from pathlib import Path
from bio_writer import build_biography

BASE = Path(__file__).parent
input_path = (BASE / "people.jsonl").resolve()
output_path = (BASE / "biografias.txt").resolve()

def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[AVISO] Linha {lineno} inválida no JSONL: {e}")
                continue

def main():
    print(f"[INFO] Lendo de: {input_path}")
    print(f"[INFO] Vai escrever em: {output_path}")

    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_path}")

    bios = []
    for person in read_jsonl(input_path):
        try:
            bio = build_biography(person)
            bios.append(bio)
        except Exception as e:
            pid = person.get("id") or person.get("name")
            print(f"[AVISO] Falha ao gerar biografia para {pid}: {e}")

    # escrita atômica para evitar arquivo “preso”
    tmp_path = output_path.with_suffix(".tmp")
    tmp_path.write_text("\n\n---\n\n".join(bios) + "\n", encoding="utf-8")
    tmp_path.replace(output_path)

    print(f"[OK] Gerado: {output_path} ({len(bios)} biografia(s))")

if __name__ == "__main__":
    main()
