# main.py (robusto para .jsonl e .json, com logs e escrita atômica)
import json
from pathlib import Path
from bio_writer import build_biography

BASE = Path(__file__).parent
input_path = (BASE / "people.jsonl").resolve()  # pode apontar para .json também
output_path = (BASE / "biografias.txt").resolve()

def _clean_line(s: str) -> str:
    # Remove BOM, espaços e vírgula final (caso alguém tenha salvo "objeto," por linha)
    s = s.replace("\ufeff", "").strip()
    if s.endswith(","):
        s = s[:-1].rstrip()
    return s

def _iter_people(path: Path):
    """
    Tenta, nesta ordem:
      1) JSON Lines (um objeto por linha).
      2) JSON normal contendo uma LISTA de objetos.
      3) JSON normal contendo um ÚNICO objeto.
    """
    text = path.read_text(encoding="utf-8-sig")
    # 1) tentar como JSONL
    ok = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _clean_line(raw)
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                ok += 1
                yield obj, f"{path}:{lineno}"
            else:
                # não é objeto; falha silenciosa para tentar modo JSON
                ok = 0
                break
        except json.JSONDecodeError:
            # quebrou como JSONL → vamos cair no modo JSON
            ok = 0
            break
    if ok > 0:
        return

    # 2) tentar como JSON (array)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            for i, obj in enumerate(data, 1):
                if isinstance(obj, dict):
                    yield obj, f"{path}[{i}]"
                else:
                    print(f"[AVISO] {path}[{i}]: entrada não é objeto JSON; ignorado.")
            return
        if isinstance(data, dict):
            yield data, f"{path}"
            return
        print(f"[AVISO] {path}: JSON de topo precisa ser objeto ou lista; nada emitido.")
    except json.JSONDecodeError as e:
        print(f"[ERRO] {path}: não consegui interpretar como JSONL nem como JSON: {e}")

def main():
    print(f"[INFO] Lendo de: {input_path}")
    print(f"[INFO] Vai escrever em: {output_path}")

    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_path}")

    total, ok, falhas = 0, 0, 0
    bios = []
    for person, ctx in _iter_people(input_path):
        total += 1
        try:
            bio = build_biography(person)
            bios.append(bio)
            ok += 1
        except Exception as e:
            pid = person.get("henry_number") or person.get("name") or "?"
            import traceback
            print(f"[AVISO] {ctx}: falha ao gerar biografia para {pid}: {e}")
            traceback.print_exc()

    if not bios:
        print("[ALERTA] Nenhuma biografia gerada. Verifique os avisos acima e o formato do arquivo.")
    else:
        # escrita atômica
        tmp_path = output_path.with_suffix(".tmp")
        tmp_path.write_text("\n\n---\n\n".join(bios) + "\n", encoding="utf-8")
        tmp_path.replace(output_path)
        print(f"[OK] Gerado: {output_path} ({len(bios)} biografia(s))")

    print(f"[INFO] Entradas lidas: {total} | Sucesso: {ok} | Falhas: {falhas}")

if __name__ == "__main__":
    main()
