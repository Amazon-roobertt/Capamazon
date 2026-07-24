"""
update_cap.py — Abre CRISP em janela separada, espera auth Midway, baixa CSV, processa e pusha.

Fluxo:
1. Abre Chrome SEPARADO (nao conflita com seu Chrome principal)
2. Navega para CRISP → cai no Midway
3. PAUSA: voce autentica manualmente
4. Aperta ENTER no terminal
5. Script continua: Search → CSV → processa → push
6. Fecha o Chrome da automacao

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

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("ERRO: pip install selenium webdriver-manager")
    sys.exit(1)

# === CONFIG ===
REPO_PATH = r"C:\Users\roobertt\Documents\Capamazon"
OUTPUT_DIR = os.path.join(REPO_PATH, "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "cap-data.json")
GIT_EXE = r"C:\Users\roobertt\AppData\Local\Programs\Git\cmd\git.exe"
# Perfil SEPARADO para automacao (nao conflita com Chrome principal)
AUTOMATION_PROFILE = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "AutomationProfile")
DOWNLOAD_DIR = os.path.join(os.environ["TEMP"], "cap_csv_download")

NODES = "SBZ2  STA9  SCZ9  SRP9  SBU9  STT9  SFC9  SSC9  SSJ9  SBT9  SBP9  SFC9  SOG9  SFM9  SDV9  SXPP  STI9  SIO9  STU9  SOS9   POP2    PJB2  PML9  PMT2  PLS1  PFE1  PLO1  EXTR  PGL2  SUN9 SUU9 "


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
    """Abre Chrome separado, espera Midway auth, baixa CSV."""
    url = build_crisp_url()
    today = datetime.now()
    end_date = today + timedelta(days=7)
    
    print(f"\n  Periodo: {today.strftime('%d/%m/%Y')} ate {end_date.strftime('%d/%m/%Y')}")
    
    # Preparar pasta de download limpa
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try: os.remove(f)
        except: pass
    
    # Configurar Chrome com perfil SEPARADO (nao interfere no Chrome principal)
    options = Options()
    options.add_argument(f"--user-data-dir={AUTOMATION_PROFILE}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1200,800")
    options.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    })
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    print(f"\n[{datetime.now():%H:%M:%S}] Abrindo Chrome (janela separada)...")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"ERRO ao abrir Chrome: {e}")
        return None
    
    try:
        # Navegar para CRISP
        print(f"[{datetime.now():%H:%M:%S}] Navegando para CRISP...")
        driver.get(url)
        time.sleep(5)
        
        # Verificar se caiu no Midway
        current = driver.current_url
        if "crisp" not in current.lower() or "midway" in current.lower() or "login" in current.lower() or "auth" in current.lower():
            print()
            print("=" * 50)
            print("  MIDWAY: Autentique na janela do Chrome")
            print("  (usuario + senha + MFA)")
            print("=" * 50)
            print()
            input("  >>> Pressione ENTER aqui quando terminar de autenticar... ")
            print()
            
            # Apos auth, o Chrome deve redirecionar para o CRISP
            time.sleep(5)
            current = driver.current_url
            
            # Se ainda nao voltou pro CRISP, navegar de novo
            if "crisp" not in current.lower():
                print(f"[{datetime.now():%H:%M:%S}] Renavegando para CRISP...")
                driver.get(url)
                time.sleep(10)
        
        print(f"[{datetime.now():%H:%M:%S}] CRISP carregado!")
        
        # Esperar pagina renderizar dados
        print(f"[{datetime.now():%H:%M:%S}] Aguardando dados carregarem...")
        time.sleep(15)
        
        # Clicar Search (pode nao ser necessario se URL ja tem params)
        try:
            search_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search')]"))
            )
            search_btn.click()
            print(f"[{datetime.now():%H:%M:%S}] Search clicado!")
            time.sleep(20)  # Esperar resultados
        except:
            print(f"[{datetime.now():%H:%M:%S}] Search nao encontrado (dados ja carregados)")
            time.sleep(5)
        
        # Clicar CSV
        print(f"[{datetime.now():%H:%M:%S}] Procurando botao CSV...")
        csv_btn = None
        selectors = [
            "//button[text()='CSV']",
            "//button[contains(text(), 'CSV')]",
            "//a[text()='CSV']",
            "//a[contains(text(), 'CSV')]",
            "//*[text()='CSV']",
        ]
        for sel in selectors:
            try:
                csv_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, sel))
                )
                break
            except:
                continue
        
        if not csv_btn:
            print("ERRO: Botao CSV nao encontrado!")
            print("  Tente clicar manualmente no CSV na janela do Chrome.")
            input("  >>> Pressione ENTER quando o CSV for baixado... ")
        else:
            csv_btn.click()
            print(f"[{datetime.now():%H:%M:%S}] CSV clicado!")
        
        # Esperar download completar
        print(f"[{datetime.now():%H:%M:%S}] Aguardando download (10s)...")
        time.sleep(10)
        
        # Verificar se baixou
        csvs = glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
        
        # Se nao encontrou na pasta configurada, checar Downloads padrao
        if not csvs:
            downloads_default = os.path.join(os.environ["USERPROFILE"], "Downloads")
            csvs = glob.glob(os.path.join(downloads_default, "standard-pickup-resources*.csv"))
            if csvs:
                # Pegar o mais recente (ultimos 2 minutos)
                now = time.time()
                csvs = [f for f in csvs if now - os.path.getmtime(f) < 120]
        
        driver.quit()
        
        if csvs:
            csv_file = max(csvs, key=os.path.getmtime)
            print(f"[{datetime.now():%H:%M:%S}] CSV baixado: {os.path.basename(csv_file)} ({os.path.getsize(csv_file)//1024} KB)")
            return csv_file
        else:
            print("ERRO: CSV nao encontrado apos download.")
            return None
            
    except Exception as e:
        print(f"ERRO: {e}")
        try: driver.quit()
        except: pass
        return None


def process_csv(csv_path):
    """Processa CSV do CRISP."""
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
    print(f"  {days} dias, {nodes} registros node/dia")
    for dk in sorted(multi_day_data.keys()):
        print(f"    {dk}: {len(multi_day_data[dk])} nodes")
    
    return {"generatedAt": datetime.now().isoformat(), "data": multi_day_data}


def save_json(data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[{datetime.now():%H:%M:%S}] JSON salvo ({os.path.getsize(OUTPUT_FILE)//1024} KB)")


def git_push():
    print(f"[{datetime.now():%H:%M:%S}] Git push...")
    def run(*args):
        return subprocess.run([GIT_EXE]+list(args), capture_output=True, text=True, cwd=REPO_PATH)
    run("add", "data/cap-data.json")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    c = run("commit", "-m", f"Auto-update CAP ({ts})")
    if "nothing to commit" in (c.stdout or ""):
        print("  Sem mudancas."); return
    p = run("push", "origin", "main")
    print(f"[{datetime.now():%H:%M:%S}] Push {'OK!' if p.returncode==0 else 'ERRO: '+p.stderr}")


def main():
    print("=" * 50)
    print("  CAP Diario - CRISP Automation")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 50)
    
    csv_path = download_csv()
    if not csv_path:
        print("\nFALHA: Nao conseguiu baixar o CSV.")
        sys.exit(1)
    
    data = process_csv(csv_path)
    if not data["data"]:
        print("CSV sem dados."); sys.exit(1)
    
    save_json(data)
    git_push()
    
    print()
    print("=" * 50)
    print("  CONCLUIDO!")
    print("  https://amazon-roobertt.github.io/Capamazon/")
    print("=" * 50)


if __name__ == "__main__":
    main()
