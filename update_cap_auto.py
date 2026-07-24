"""
update_cap_auto.py — Versão SILENCIOSA para Task Scheduler.
Se Midway expirou, sai sem travar (tenta no próximo horário).
Se cookie válido, roda 100% sozinho.

Task Scheduler: 13h, 15h, 17h, 19h seg-sex
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

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    sys.exit(1)

# === CONFIG ===
REPO_PATH = r"C:\Users\roobertt\Documents\Capamazon"
OUTPUT_DIR = os.path.join(REPO_PATH, "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "cap-data.json")
GIT_EXE = r"C:\Users\roobertt\AppData\Local\Programs\Git\cmd\git.exe"
AUTOMATION_PROFILE = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "AutomationProfile")
DOWNLOAD_DIR = os.path.join(os.environ["TEMP"], "cap_csv_download")
LOG_FILE = os.path.join(REPO_PATH, "update_log.txt")

NODES = "SBZ2  STA9  SCZ9  SRP9  SBU9  STT9  SFC9  SSC9  SSJ9  SBT9  SBP9  SFC9  SOG9  SFM9  SDV9  SXPP  STI9  SIO9  STU9  SOS9   POP2    PJB2  PML9  PMT2  PLS1  PFE1  PLO1  EXTR  PGL2  SUN9 SUU9 "


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


def build_crisp_url():
    today = datetime.now()
    end_date = today + timedelta(days=7)
    start_str = today.strftime("%Y-%m-%dT00:00")
    end_str = end_date.strftime("%Y-%m-%dT23:59")
    base = "https://crisp-na.corp.amazon.com/transportation/capacity-dashboard"
    params = (
        f"?timeRangeStart={start_str}"
        f"&timeRangeEnd={end_str}"
        f"&zoneId=America/Sao_Paulo"
        f"&pickupSourceWarehouses={NODES}"
        f"&pickupDestinationWarehouses="
        f"&pickupShipMethods=AMZL_BR_NEXT"
        f"&pickupSortCodes=&pickupShippingLanes=&pickupShipOptionGroups="
        f"&pickupProcessingCapabilities=&pickupWarehouseCycles=&pickupConditionNames="
        f"&deliveryCarrierDeliveryAreas=&deliveryShipOptionGroups=&deliveryConditionNames="
        f"&constraints=SoftCap&constraints=Monitor"
        f"&units=PkgCount&units=CUBIC_VOLUME"
    )
    return base + params


def download_csv():
    """Abre Chrome com perfil de automacao. Se Midway expirou, retorna None (nao trava)."""
    url = build_crisp_url()
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try: os.remove(f)
        except: pass
    
    options = Options()
    options.add_argument(f"--user-data-dir={AUTOMATION_PROFILE}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_argument("--headless=new")  # Modo headless (sem janela visivel)
    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    })
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    log("Iniciando Chrome (headless)...")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        log(f"ERRO Chrome: {e}")
        return None
    
    try:
        driver.get(url)
        time.sleep(10)
        
        # Verificar Midway
        current = driver.current_url
        if "crisp" not in current.lower() or "midway" in current.lower() or "login" in current.lower():
            log("SKIP: Cookie Midway expirado. Rode Atualizar_CAP.bat manualmente para renovar.")
            driver.quit()
            return None
        
        log("CRISP carregado (cookie valido)")
        
        # Esperar dados
        time.sleep(15)
        
        # Clicar Search
        try:
            search_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search')]"))
            )
            search_btn.click()
            log("Search clicado")
            time.sleep(20)
        except:
            log("Search nao encontrado (dados ja carregados)")
            time.sleep(5)
        
        # Clicar CSV
        csv_btn = None
        for sel in ["//button[text()='CSV']", "//button[contains(text(), 'CSV')]", "//*[text()='CSV']"]:
            try:
                csv_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, sel))
                )
                break
            except:
                continue
        
        if not csv_btn:
            log("ERRO: Botao CSV nao encontrado")
            driver.quit()
            return None
        
        csv_btn.click()
        log("CSV clicado")
        time.sleep(10)
        
        driver.quit()
        
        # Encontrar CSV baixado
        csvs = glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
        if csvs:
            csv_file = max(csvs, key=os.path.getmtime)
            log(f"CSV: {os.path.basename(csv_file)} ({os.path.getsize(csv_file)//1024} KB)")
            return csv_file
        
        log("ERRO: CSV nao encontrado na pasta de download")
        return None
        
    except Exception as e:
        log(f"ERRO: {e}")
        try: driver.quit()
        except: pass
        return None


def process_csv(csv_path):
    """Processa CSV do CRISP."""
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
            total_reserved_str = row.get("Total reserved", "").strip()
            capacity_value_str = row.get("Capacity value", "").strip()
            
            if cond == "AMZL_OVERSIZE_BR":
                continue
            node_name = sour
            if sort_code in ("EX", "EXTR"):
                node_name = sort_code
            if not node_name or not date_val:
                continue
            
            is_cubic = (measurement == "Cubic feet" and constraint == "Monitor")
            is_pkg = (measurement == "Package count" and constraint == "Soft cap")
            if not is_cubic and not is_pkg:
                continue
            
            # AMBOS usam Total reserved (mesma logica do HTML original)
            try: val = float(total_reserved_str) if total_reserved_str else 0
            except: val = 0
            if val == 0: continue
            
            if date_val not in multi_day_data:
                multi_day_data[date_val] = {}
            if node_name not in multi_day_data[date_val]:
                multi_day_data[date_val][node_name] = {"cubicFeet": 0, "cap": 0, "hasCap": False}
            
            if is_cubic:
                multi_day_data[date_val][node_name]["cubicFeet"] += val
            elif is_pkg:
                if not multi_day_data[date_val][node_name]["hasCap"]:
                    multi_day_data[date_val][node_name]["cap"] = val
                    multi_day_data[date_val][node_name]["hasCap"] = True
    
    for d in multi_day_data:
        for n in multi_day_data[d]:
            del multi_day_data[d][n]["hasCap"]
    
    days = len(multi_day_data)
    nodes = sum(len(v) for v in multi_day_data.values())
    log(f"Processado: {days} dias, {nodes} registros")
    return {"generatedAt": datetime.now().isoformat(), "data": multi_day_data}


def save_json(data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    log(f"JSON salvo ({os.path.getsize(OUTPUT_FILE)//1024} KB)")


def git_push():
    def run(*args):
        return subprocess.run([GIT_EXE]+list(args), capture_output=True, text=True, cwd=REPO_PATH)
    run("add", "data/cap-data.json")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    c = run("commit", "-m", f"Auto-update CAP ({ts})")
    if "nothing to commit" in (c.stdout or ""):
        log("Sem mudancas nos dados")
        return
    p = run("push", "origin", "main")
    log(f"Push {'OK' if p.returncode==0 else 'ERRO: '+p.stderr}")


def main():
    log("=== CAP Auto Update START ===")
    
    csv_path = download_csv()
    if not csv_path:
        log("=== SKIP (sem CSV) ===")
        sys.exit(0)  # Exit 0 para nao marcar como erro no Task Scheduler
    
    data = process_csv(csv_path)
    if not data["data"]:
        log("CSV vazio")
        sys.exit(0)
    
    save_json(data)
    git_push()
    log("=== CAP Auto Update DONE ===")


if __name__ == "__main__":
    main()
