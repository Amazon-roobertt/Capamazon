"""
update_cap.py — Processa CSV do CRISP (standard-pickup-resources.csv) e pusha para GitHub Pages.

Fluxo:
1. Busca o CSV mais recente na pasta Downloads (standard-pickup-resources*.csv)
2. Processa (mesma logica do HTML LogiVision)
3. Gera data/cap-data.json
4. Git push para GitHub Pages

Uso: python update_cap.py
"""

import csv
import glob
import json
import os
import subprocess
import sys
from datetime import datetime

# === CONFIG ===
REPO_PATH = r"C:\Users\roobertt\Documents\Capamazon"
OUTPUT_DIR = os.path.join(REPO_PATH, "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "cap-data.json")
GIT_EXE = r"C:\Users\roobertt\AppData\Local\Programs\Git\cmd\git.exe"
DOWNLOAD_DIR = os.path.join(os.environ["USERPROFILE"], "Downloads")


def find_latest_csv():
    """Encontra o CSV mais recente do CRISP na pasta Downloads."""
    pattern = os.path.join(DOWNLOAD_DIR, "standard-pickup-resources*.csv")
    files = glob.glob(pattern)
    
    if not files:
        print("ERRO: Nenhum arquivo 'standard-pickup-resources*.csv' encontrado em Downloads.")
        print("  Baixe o CSV do CRISP primeiro.")
        return None
    
    # Pegar o mais recente
    latest = max(files, key=os.path.getmtime)
    age_min = (datetime.now().timestamp() - os.path.getmtime(latest)) / 60
    
    print(f"  CSV encontrado: {os.path.basename(latest)}")
    print(f"  Tamanho: {os.path.getsize(latest)//1024} KB")
    print(f"  Idade: {age_min:.0f} minutos")
    
    if age_min > 60:
        print(f"  AVISO: CSV tem mais de 1 hora. Considere baixar um novo.")
    
    return latest


def process_csv(csv_path):
    """Processa CSV do CRISP (mesma logica do HTML LogiVision CAP)."""
    print(f"[{datetime.now():%H:%M:%S}] Processando CSV...")
    
    multi_day_data = {}
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            sour = row.get("Sour", "").strip()
            sort_code = row.get("Sort code", "").strip()
            cond = row.get("Cond", "").strip()
            date_val = row.get("Date", "").strip()
            measurement = row.get("Measurement", "").strip()
            constraint = row.get("Constraint", "").strip()
            
            # O CSV do CRISP usa "Total reserved" como valor principal
            # e "Capacity value" como o limite (cap) para Soft cap
            total_reserved_str = row.get("Total reserved", "").strip()
            capacity_value_str = row.get("Capacity value", "").strip()
            
            # Skip AMZL_OVERSIZE_BR
            if cond == "AMZL_OVERSIZE_BR":
                continue
            
            # Determinar node name
            node_name = sour
            if sort_code in ("EX", "EXTR"):
                node_name = sort_code
            
            if not node_name or not date_val:
                continue
            
            # Filtrar: Cubic feet + Monitor OU Package count + Soft cap
            is_cubic_feet = (measurement == "Cubic feet" and constraint == "Monitor")
            is_package_count = (measurement == "Package count" and constraint == "Soft cap")
            
            if not is_cubic_feet and not is_package_count:
                continue
            
            # Para Cubic feet: usar Total reserved
            # Para Package count + Soft cap: usar Capacity value como CAP
            # AMBOS usam Total reserved (mesma logica do HTML original)
            try:
                val = float(total_reserved_str) if total_reserved_str else 0
            except (ValueError, TypeError):
                val = 0
            if val == 0:
                continue
            
            # Inicializar estrutura
            if date_val not in multi_day_data:
                multi_day_data[date_val] = {}
            if node_name not in multi_day_data[date_val]:
                multi_day_data[date_val][node_name] = {"cubicFeet": 0, "cap": 0, "hasCap": False}
            
            if is_cubic_feet:
                multi_day_data[date_val][node_name]["cubicFeet"] += val
            elif is_package_count:
                # Deduplicacao: apenas primeiro valor de CAP por node/dia
                if not multi_day_data[date_val][node_name]["hasCap"]:
                    multi_day_data[date_val][node_name]["cap"] = val
                    multi_day_data[date_val][node_name]["hasCap"] = True
    
    # Limpar flag hasCap
    for date_key in multi_day_data:
        for node in multi_day_data[date_key]:
            del multi_day_data[date_key][node]["hasCap"]
    
    total_days = len(multi_day_data)
    total_nodes = sum(len(nodes) for nodes in multi_day_data.values())
    print(f"  {total_days} dias processados")
    print(f"  {total_nodes} registros node/dia")
    
    # Mostrar resumo por dia
    for date_key in sorted(multi_day_data.keys()):
        nodes_count = len(multi_day_data[date_key])
        print(f"    {date_key}: {nodes_count} nodes")
    
    return {"generatedAt": datetime.now().isoformat(), "data": multi_day_data}


def save_json(data):
    """Salva JSON no repo."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"[{datetime.now():%H:%M:%S}] JSON salvo: {size_kb:.1f} KB")


def git_push():
    """Git add, commit, push."""
    print(f"[{datetime.now():%H:%M:%S}] Git push...")
    
    def run_git(*args):
        return subprocess.run([GIT_EXE] + list(args), capture_output=True, text=True, cwd=REPO_PATH)
    
    run_git("add", "data/cap-data.json")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit = run_git("commit", "-m", f"Auto-update CAP ({timestamp})")
    
    if "nothing to commit" in (commit.stdout or ""):
        print("  Sem alteracoes nos dados.")
        return
    
    push = run_git("push", "origin", "main")
    if push.returncode == 0:
        print(f"[{datetime.now():%H:%M:%S}] Push OK!")
    else:
        print(f"  ERRO push: {push.stderr}")


def main():
    print("=" * 50)
    print("CAP Diario - Update from CRISP CSV")
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 50)
    
    csv_path = find_latest_csv()
    if not csv_path:
        sys.exit(1)
    
    data = process_csv(csv_path)
    
    if not data["data"]:
        print("ERRO: CSV processado mas sem dados validos.")
        sys.exit(1)
    
    save_json(data)
    git_push()
    
    print("=" * 50)
    print("CONCLUIDO! Dashboard atualizado.")
    print("URL: https://amazon-roobertt.github.io/Capamazon/")
    print("=" * 50)


if __name__ == "__main__":
    main()
