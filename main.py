import os
import re
import time
import requests
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from mailtm import Email

# --- 1. DATE & PAGINATION LOGIC ---
# This ensures we pick a new set of 50 leads every day automatically
start_date = datetime(2026, 3, 23)
base_value = 50
today = datetime.now()
days_passed = (today - start_date).days
a = base_value + (days_passed * 50)

page = (a // 500) + 1
start_in_page = a % 500
end_in_page = start_in_page + 50

# --- 2. CHROME CONFIGURATION ---
options = webdriver.ChromeOptions()
options.add_argument("--headless=new") # Required for GitHub Actions
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

service = Service(ChromeDriverManager().install())

def run_full_automation():
    # Setup Temp Email
    mailbox = Email()
    mailbox.register()
    email_addr = mailbox.address
    print(f"[*] Generated Email: {email_addr}")

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 40) # Increased timeout for slow server responses
    
    try:
        print("[*] Navigating to Login...")
        driver.get("https://leadrocks.io/login")

        # Enter Email
        email_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type=email]")))
        email_input.send_keys(email_addr)
        
        # Click Next
        next_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Next')]")
        driver.execute_script("arguments[0].click();", next_btn)
        print("[*] Email submitted. Waiting for PIN...")

        def on_message(message):
            print("\n[!] PIN Email Received!")
            match = re.search(r'\b\d{5}\b', message['text'])
            
            if match:
                pin_code = match.group()
                print(f"[!] Extracted PIN: {pin_code}")
                
                try:
                    # 1. Enter PIN and Login
                    pin_field = wait.until(EC.element_to_be_clickable((By.NAME, "pin")))
                    pin_field.send_keys(pin_code)
                    time.sleep(2)
                    pin_field.send_keys(u'\ue007') # Press Enter Key
                    print("[*] Logged in. Waiting for dashboard...")

                    # 2. Navigate to Search
                    time.sleep(7)
                    search_url = f"https://leadrocks.io/my?position=morocco&pp=500&p={page}"
                    print(f"[*] Navigating to Search: {search_url}")
                    driver.get(search_url)

                    # 3. Select Checkboxes
                    print("[*] Waiting for lead table...")
                    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td input[type='checkbox']")))
                    checkboxes = driver.find_elements(By.CSS_SELECTOR, "td input[type='checkbox']")
                    
                    target_boxes = checkboxes[start_in_page:end_in_page]
                    print(f"[*] Selecting leads {start_in_page} to {end_in_page}...")
                    
                    for box in target_boxes:
                        try:
                            driver.execute_script("arguments[0].click();", box)
                        except: continue

                    # 4. Save to List
                    print("[*] Saving to Default List...")
                    save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Open and save selected']")))
                    driver.execute_script("arguments[0].click();", save_button)
                    
                    list_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'leads-lists')]//button[normalize-space()='Default list']")))
                    driver.execute_script("arguments[0].click();", list_button)
                    
                    print("[*] Saved. Waiting 10s for database synchronization...")
                    time.sleep(10)

                    # 5. Scrape Saved Leads
                    print("[*] Navigating to My Leads...")
                    driver.get('https://leadrocks.io/my/leads')
                    
                    # Ensure table exists before trying to interact
                    try:
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr[data-id]")))
                        dropdown = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "per_page")))
                        Select(dropdown).select_by_value("500")
                        time.sleep(5)
                    except Exception as table_err:
                        print(f"[!] Warning: Table issue: {table_err}")

                    rows = driver.find_elements(By.CSS_SELECTOR, "tr[data-id]")
                    print(f"[*] Found {len(rows)} rows. Starting Scrape...")

                    leads_to_send = []
                    for row in rows:
                        try:
                            # Extract data with safety fallbacks
                            name_el = row.find_elements(By.TAG_NAME, "h3")
                            email_el = row.find_elements(By.CLASS_NAME, "label_work")
                            title_el = row.find_elements(By.TAG_NAME, "small")
                            comp_el = row.find_elements(By.TAG_NAME, "h4")
                            link_el = row.find_elements(By.CLASS_NAME, "li")

                            leads_to_send.append({
                                "Name": name_el[0].text if name_el else "Unknown",
                                "Job_Title": title_el[0].text if title_el else "N/A",
                                "Company": comp_el[0].text if comp_el else "N/A",
                                "Email": email_el[0].text if email_el else "N/A",
                                "LinkedIn": link_el[0].get_attribute("href") if link_el else "N/A",
                                "Country": "Maroc"
                            })
                        except Exception as row_e:
                            print(f"[-] Skipped a row due to error: {row_e}")
                            continue

                    # 6. WEBHOOK DISPATCH (Non-Blocking)
                    WEBHOOK_URL = "https://ai.targetupconsulting.com/webhook-test/8c6f756c-52a3-436e-a56e-741accff5710"
                    print(f"🚀 Attempting to send {len(leads_to_send)} leads to Webhook...")
                    
                    for idx, payload in enumerate(leads_to_send):
                        try:
                            # We use a shorter timeout for webhook to keep script moving
                            response = requests.post(WEBHOOK_URL, json=payload, timeout=15)
                            if response.status_code == 200:
                                print(f"✅ Lead {idx+1}/{len(leads_to_send)} sent: {payload['Name']}")
                            else:
                                print(f"⚠️ Lead {idx+1} Webhook returned status: {response.status_code}")
                        except Exception as webhook_error:
                            # IF WEBHOOK FAILS, WE ONLY PRINT AND CONTINUE
                            print(f"❌ WEBHOOK FAILED for {payload['Name']}: {webhook_error}")
                            print("[*] Continuing to next lead...")

                    print("\n[FINISH] All automation steps completed.")
                    mailbox.stop()
                    os._exit(0) # Properly kill all threads and exit

                except Exception as e:
                    print(f"[CRITICAL CALLBACK ERROR] {e}")

        # Start the background listener
        mailbox.start(on_message, interval=5)
        
        # Keep main script alive for up to 8 minutes
        print("[*] Main thread sleeping, waiting for callback to finish...")
        time.sleep(480)

    except Exception as e:
        print(f"[GLOBAL SCRIPT ERROR] {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_full_automation()
