"""
update_cap.py — Acessa CRISP, baixa CSV de capacity, processa e pusha para GitHub Pages.

Requisitos:
- VPN Amazon conectada
- Midway autenticado (Chrome com sessao ativa)
- pip install selenium webdriver-manager

Uso: python update_cap.py
"""

import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("ERRO: selenium ou webdriver-manager nao instalado.")
    print("Rode: pip install selenium webdriver-manager")
    sys.exit(1)

# === CONFIGURACAO ===
REPO_PATH = r"C:\Users\roobertt\Documents\Capamazon"
OUTPUT_DIR = os.path.join(REPO_PATH, "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "cap-data.json")
GIT_EXE = r"C:\Users\roobertt\AppData\Local\Programs\Git\cmd\git.exe"
CHROME_PROFILE = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")
DOWNLOAD_DIR = os.path.join(os.environ["USERPROFILE"], "Downloads")

# Nodes filtrados no CRISP
NODES = "SBZ2  STA9  SCZ9  SRP9  SBU9  STT9  SFC9  SSC9  SSJ9  SBT9  SBP9  SFC9  SOG9  SFM9  SDV9  SXPP  STI9  SIO9  STU9  SOS9   POP2    PJB2  PML9  PMT2  PLS1  PFE1  PLO1  EXTR  PGL2  SUN9 SUU9 "

def build_crisp_url():
    """Gera a URL do CRISP com datas de amanha ate amanha+7."""
    tomorrow = datetime.now() + timedelta(days=1)
    end_date = tomorrow + timedelta(days=6)
    
    # Formato: 2026-07-25T00:00
    start_str = tomorrow.strftime("%Y-%m-%dT00:00")
    end_str = end_date.strftime("%Y-%m-%dT23:59")
    
    base = "https://crisp-na.corp.amazon.com/transportation/capacity-dashboard"
    params = (
        f"?timeRangeStart={start_str}"
        f"&timeRangeEnd={end_str}"
        f"&zoneId=America/Sao_Paulo"
        f"&pickupSourceWarehouses={NODES}"
        f"&pickupDestinationWarehouses="
        f"&pickupShipMethods=AMZL_BR_NEXT"
        f"&pickupSortCodes="
        f"&pickupShippingLanes="
        f"&pickupShipOptionGroups="
        f"&pickupProcessingCapabilities="
        f"&pickupWarehouseCycles="
        f"&pickupConditionNames="
        f"&deliveryCarrierDeliveryAreas="
        f"&deliveryShipOptionGroups="
        f"&deliveryConditionNames="
        f"&constraints=SoftCap"
        f"&constraints=Monitor"
        f"&units=PkgCount"
        f"&units=CUBIC_VOLUME"
    )
    return base + params


def get_latest_csv():
    """Encontra o CSV mais recente baixado do CRISP."""
    # CRISP baixa como "capacity-dashboard*.csv" ou similar
    patterns = [
        os.path.join(DOWNLOAD_DIR, "capacity*dashboard*.csv"),
        os.path.join(DOWNLOAD_DIR, "capacity*.csv"),
        os.path.join(DOWNLOAD_DIR, "*.csv"),
    ]
    
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    
    if not candidates:
        return None
    
    # Pegar o mais recente (modificado nos ultimos 5 minutos)
    now = time.time()
    recent = [f for f in candidates if now - os.path.getmtime(f) < 300]
    
    if not recent:
        return None
    
    return max(recent, key=os.path.getmtime)


def download_csv_from_crisp():
    """Abre CRISP com Selenium, espera carregar, clica em CSV."""
    url = build_crisp_url()
    print(f"[{datetime.now():%H:%M:%S}] URL: {url[:100]}...")
    
    # Limpar CSVs antigos do CRISP na pasta Downloads
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "capacity*.csv")):
        try:
            os.remove(f)
        except:
            pass
    
    # Configurar Chrome com perfil do usuario (cookies Midway)
    options = Options()
    options.add_argument(f"--user-data-dir={CHROME_PROFILE}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
    })
    # Headless nao funciona bem com Midway, usar headed mas minimizado
    options.add_argument("--start-minimized")
    
    print(f"[{datetime.now():%H:%M:%S}] Abrindo Chrome com perfil Midway...")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"ERRO ao abrir Chrome: {e}")
        print("Dica: Feche TODAS as janelas do Chrome antes de rodar o script.")
        return None
    
    try:
        # Navegar para o CRISP
        print(f"[{datetime.now():%H:%M:%S}] Navegando para CRISP...")
        driver.get(url)
        
        # Esperar a pagina carregar (buscar botao Search ou tabela)
        print(f"[{datetime.now():%H:%M:%S}] Aguardando pagina carregar...")
        time.sleep(10)  # CRISP eh lento
        
        # Tentar clicar no botao Search (pode ja estar carregado pela URL)
        try:
            search_btn = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search')]"))
            )
            search_btn.click()
            print(f"[{datetime.now():%H:%M:%S}] Clicou em Search...")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] Search button nao encontrado ou ja executado: {e}")
        
        # Esperar dados carregarem
        print(f"[{datetime.now():%H:%M:%S}] Aguardando dados carregarem...")
        time.sleep(15)
        
        # Clicar no botao CSV
        try:
            csv_btn = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'CSV')]"))
            )
            csv_btn.click()
            print(f"[{datetime.now():%H:%M:%S}] Clicou em CSV...")
        except Exception as e:
            print(f"ERRO: Botao CSV nao encontrado: {e}")
            driver.quit()
            return None
        
        # Esperar download completar
        print(f"[{datetime.now():%H:%M:%S}] Aguardando download...")
        time.sleep(10)
        
        driver.quit()
        
        # Encontrar o CSV baixado
        csv_file = get_latest_csv()
        if csv_file:
            print(f"[{datetime.now():%H:%M:%S}] CSV baixado: {csv_file}")
            return csv_file
        else:
            print("ERRO: CSV nao encontrado apos download.")
            return None
            
    except Exception as e:
        print(f"ERRO durante navegacao: {e}")
        driver.quit()
        return None


def process_csv(csv_path):
    """Processa o CSV do CRISP (mesma logica do HTML LogiVision)."""
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
            total_reserved = row.get("Total reserved", "").strip()
            
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
            
            try:
                val_s = float(total_reserved)
            except (ValueError, TypeError):
                continue
            
            if val_s == 0:
                continue
            
            # Inicializar estrutura
            if date_val not in multi_day_data:
                multi_day_data[date_val] = {}
            if node_name not in multi_day_data[date_val]:
                multi_day_data[date_val][node_name] = {"cubicFeet": 0, "cap": 0, "hasCap": False}
            
            if is_cubic_feet:
                multi_day_data[date_val][node_name]["cubicFeet"] += val_s
            elif is_package_count:
                # Deduplicacao: manter apenas primeiro valor de CAP por node/dia
                if not multi_day_data[date_val][node_name]["hasCap"]:
                    multi_day_data[date_val][node_name]["cap"] = val_s
                    multi_day_data[date_val][node_name]["hasCap"] = True
    
    # Limpar flag hasCap antes de salvar
    for date_key in multi_day_data:
        for node in multi_day_data[date_key]:
            if "hasCap" in multi_day_data[date_key][node]:
                del multi_day_data[date_key][node]["hasCap"]
    
    total_days = len(multi_day_data)
    total_nodes = sum(len(nodes) for nodes in multi_day_data.values())
    print(f"  {total_days} dias, {total_nodes} registros node-dia")
    
    return {
        "generatedAt": datetime.now().isoformat(),
        "data": multi_day_data
    }


def save_json(data):
    """Salva JSON no repo."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    
    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"[{datetime.now():%H:%M:%S}] JSON salvo: {OUTPUT_FILE} ({size_kb:.1f} KB)")


def git_push():
    """Git add, commit, push."""
    print(f"[{datetime.now():%H:%M:%S}] Git push...")
    
    def run_git(*args):
        result = subprocess.run(
            [GIT_EXE] + list(args),
            capture_output=True, text=True, cwd=REPO_PATH
        )
        return result
    
    run_git("add", "data/cap-data.json")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_result = run_git("commit", "-m", f"Auto-update CAP data ({timestamp})")
    
    if "nothing to commit" in (commit_result.stdout or ""):
        print("  Sem alteracoes nos dados.")
        return
    
    push_result = run_git("push", "origin", "main")
    if push_result.returncode == 0:
        print(f"[{datetime.now():%H:%M:%S}] Push OK!")
    else:
        print(f"  ERRO push: {push_result.stderr}")


def main():
    print("=" * 50)
    print("CAP Diario - Auto Update (CRISP)")
    print("=" * 50)
    
    # Baixar CSV do CRISP
    csv_path = download_csv_from_crisp()
    
    if not csv_path:
        print("FALHA: Nao foi possivel baixar o CSV do CRISP.")
        print("Verifique: VPN conectada? Midway autenticado? Chrome fechado?")
        sys.exit(1)
    
    # Processar
    data = process_csv(csv_path)
    
    if not data["data"]:
        print("AVISO: CSV processado mas sem dados validos.")
        sys.exit(1)
    
    # Salvar e pushar
    save_json(data)
    git_push()
    
    # Limpar CSV baixado
    try:
        os.remove(csv_path)
    except:
        pass
    
    print("=" * 50)
    print("CONCLUIDO!")
    print("=" * 50)


if __name__ == "__main__":
    main()
