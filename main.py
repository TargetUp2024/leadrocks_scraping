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

# -----------------------------
# 1. DATE LOGIC
# -----------------------------
print("[*] Calculating pagination...")
start_date = datetime(2026, 3, 23)
base_value = 50
today = datetime.now()
days_passed = (today - start_date).days
a = base_value + (days_passed * 50)

page = (a // 500) + 1
start_in_page = a % 500
end_in_page = start_in_page + 50
print(f"[*] Targeting Page: {page} | Range: {start_in_page}-{end_in_page}")

# -----------------------------
# 2. CHROME CONFIG (CI Optimized)
# -----------------------------
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
    wait = WebDriverWait(driver, 30)
    
    try:
        print("[*] Navigating to Login...")
        driver.get("https://leadrocks.io/login")

        # Submit Email
        email_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type=email]")))
        email_input.send_keys(email_addr)
        
        next_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Next')]")
        next_btn.click()
        print("[*] Waiting for PIN email...")

        def on_message(message):
            print("\n[!] PIN Email Received!")
            match = re.search(r'\b\d{5}\b', message['text'])
            
            if match:
                pin_code = match.group()
                print(f"[!] Extracted PIN: {pin_code}")
                
                try:
                    # 1. Enter PIN
                    pin_field = wait.until(EC.element_to_be_clickable((By.NAME, "pin")))
                    pin_field.clear()
                    pin_field.send_keys(pin_code)
                    print("[*] PIN entered.")

                    # 2. Robust Login Button Search (The Fix)
                    time.sleep(2) # Buffer for UI
                    print("[*] Attempting to click Login...")
                    
                    # Try class selector first, then text, then enter key
                    try:
                        # We use XPATH to find a button that contains 'gobtn' or the text 'Go'
                        go_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'gobtn') or contains(., 'Go')]")))
                        driver.execute_script("arguments[0].click();", go_button)
                    except:
                        print("[!] Button click failed, trying Enter key...")
                        pin_field.send_keys(u'\ue007') # Press Enter

                    # 3. Navigation
                    time.sleep(5)
                    search_url = f"https://leadrocks.io/my?position=morocco&pp=500&p={page}"
                    print(f"[*] Navigating to Search: {search_url}")
                    driver.get(search_url)

                    # 4. Selection
                    print("[*] Waiting for lead table...")
                    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td input[type='checkbox']")))
                    checkboxes = driver.find_elements(By.CSS_SELECTOR, "td input[type='checkbox']")
                    
                    target_boxes = checkboxes[start_in_page:end_in_page]
                    print(f"[*] Selecting leads {start_in_page} to {end_in_page}...")
                    
                    checked_count = 0
                    for box in target_boxes:
                        try:
                            driver.execute_script("arguments[0].click();", box)
                            checked_count += 1
                        except: continue

                    # 5. Save to List
                    print("[*] Saving to Default List...")
                    save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Open and save selected']")))
                    driver.execute_script("arguments[0].click();", save_button)
                    
                    list_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'leads-lists')]//button[normalize-space()='Default list']")))
                    driver.execute_script("arguments[0].click();", list_button)
                    
                    print(f"[*] Successfully saved {checked_count} leads.")
                    time.sleep(5)

                    # 6. Scrape Saved Leads
                    print("[*] Navigating to My Leads...")
                    driver.get('https://leadrocks.io/my/leads')
                    
                    dropdown_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "per_page")))
                    Select(dropdown_element).select_by_value("500")
                    time.sleep(3)

                    rows = driver.find_elements(By.CSS_SELECTOR, "tr[data-id]")
                    leads_data = []
                    for row in rows:
                        try:
                            leads_data.append({
                                "Name": row.find_element(By.TAG_NAME, "h3").text,
                                "Job_Title": row.find_element(By.TAG_NAME, "small").text,
                                "Company": row.find_element(By.TAG_NAME, "h4").text,
                                "Email": row.find_element(By.CLASS_NAME, "label_work").text,
                                "LinkedIn": row.find_element(By.CLASS_NAME, "li").get_attribute("href"),
                                "Country": "Maroc"
                            })
                        except: continue

                    print(f"[+] Scraped {len(leads_data)} leads.")

                    # 7. Webhook Dispatch
                    WEBHOOK_URL = "https://ai.targetupconsulting.com/webhook-test/8c6f756c-52a3-436e-a56e-741accff5710"
                    for idx, lead in enumerate(leads_data):
                        try:
                            requests.post(WEBHOOK_URL, json=lead, timeout=30)
                            if (idx + 1) % 10 == 0: print(f"[*] Sent {idx+1}/{len(leads_data)}")
                        except: print(f"[*] Failed to send lead {idx+1}")

                    print("✅ ALL TASKS COMPLETE")
                    mailbox.stop()
                    os._exit(0) # Exit the script once background thread is done

                except Exception as e:
                    print(f"[ERROR inside listener] {e}")

        mailbox.start(on_message, interval=5)
        
        # Keep main thread alive
        timeout_limit = 300 # 5 minutes
        start_time = time.time()
        while time.time() - start_time < timeout_limit:
            time.sleep(1)

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_full_automation()
