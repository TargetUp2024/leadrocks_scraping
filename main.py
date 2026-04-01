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

from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException
)

from webdriver_manager.chrome import ChromeDriverManager
from mailtm import Email

# -----------------------------
# DATE LOGIC
# -----------------------------
print("[*] Calculating date logic and pagination...")
start_date = datetime(2026, 3, 23)
base_value = 50
today = datetime.now()
days_passed = (today - start_date).days

a = base_value + (days_passed * 50)

page = (a // 500) + 1
start_in_page = a % 500
end_in_page = start_in_page + 50
print(f"[*] Target: Page {page} | Range: {start_in_page} to {end_in_page}")

# -----------------------------
# CHROME OPTIONS (CI SAFE)
# -----------------------------
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

service = Service(ChromeDriverManager().install())

def run_full_automation():
    print("[*] Initializing Email mailbox...")
    mailbox = Email()
    mailbox.register()
    email_addr = mailbox.address
    print(f"[*] Generated Email: {email_addr}")

    print("[*] Starting Chrome Driver...")
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    try:
        print("[*] Navigating to: https://leadrocks.io/login")
        driver.get("https://leadrocks.io/login")

        print("[*] Entering email address...")
        email_input = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type=email]"))
        )
        email_input.send_keys(email_addr)

        print("[*] Clicking 'Next' button...")
        next_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')]")))
        next_btn.click()

        print("[*] Waiting for incoming PIN email...")

        def on_message(message):
            print("\n[!] Email received! Parsing for PIN...")
            match = re.search(r"\b\d{5}\b", message["text"])

            if match:
                pin_code = match.group()
                print(f"[PIN FOUND] {pin_code}")

                try:
                    print("[*] Locating PIN input field...")
                    pin_field = wait.until(
                        EC.element_to_be_clickable((By.NAME, "pin"))
                    )
                    pin_field.send_keys(pin_code)

                    print("[*] Attempting to click Login/Submit button...")
                    # UPDATED SELECTOR: Looks for a button with text or the specific gobtn class
                    submit_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(@class, 'gobtn') or contains(., 'Login') or contains(., 'Submit')]")
                    ))
                    submit_btn.click()

                    print("[*] Login submitted. Waiting for dashboard...")
                    time.sleep(5)

                    # -----------------------------
                    # NAVIGATION
                    # -----------------------------
                    url = f"https://leadrocks.io/my?position=morocco&pp=500&p={page}"
                    print(f"[*] Navigating to Search: {url}")
                    driver.get(url)

                    print("[*] Waiting for checkboxes to load...")
                    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td input[type='checkbox']")))

                    checkboxes = driver.find_elements(By.CSS_SELECTOR, "td input[type='checkbox']")
                    target_boxes = checkboxes[start_in_page:end_in_page]

                    print(f"[*] Found {len(checkboxes)} total checkboxes. Selecting targets...")
                    checked = 0
                    for box in target_boxes:
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", box)
                            if not box.is_selected():
                                box.click()
                                checked += 1
                        except:
                            continue

                    print(f"[+] Successfully selected {checked} leads.")

                    # SAVE
                    print("[*] Clicking 'Open and save selected'...")
                    save_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[normalize-space()='Open and save selected']")
                    ))
                    save_btn.click()

                    print("[*] Selecting 'Default list'...")
                    list_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//div[contains(@class,'leads-lists')]//button[normalize-space()='Default list']")
                    ))
                    list_btn.click()

                    print("[*] Processing save (waiting 5s)...")
                    time.sleep(5)

                    # -----------------------------
                    # SCRAPE
                    # -----------------------------
                    print("[*] Navigating to Saved Leads page...")
                    driver.get("https://leadrocks.io/my/leads")

                    print("[*] Setting view to 500 per page...")
                    dropdown = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "per_page")))
                    Select(dropdown).select_by_value("500")
                    time.sleep(3)

                    rows = driver.find_elements(By.CSS_SELECTOR, "tr[data-id]")
                    print(f"[*] Scoping {len(rows)} rows for data extraction...")

                    data = []
                    for row in rows:
                        try:
                            name = row.find_element(By.TAG_NAME, "h3").text
                            job = row.find_element(By.TAG_NAME, "small").text
                            company = row.find_element(By.TAG_NAME, "h4").text

                            try:
                                email = row.find_element(By.CLASS_NAME, "label_work").text
                            except:
                                email = "N/A"

                            try:
                                linkedin = row.find_element(By.CLASS_NAME, "li").get_attribute("href")
                            except:
                                linkedin = "N/A"

                            data.append({
                                "Name": name,
                                "Job_Title": job,
                                "Company": company,
                                "Email": email,
                                "LinkedIn": linkedin,
                                "Country": "Maroc"
                            })
                        except:
                            continue

                    df = pd.DataFrame(data)
                    print(f"[+] Extracted {len(df)} leads successfully.")

                    # -----------------------------
                    # WEBHOOK
                    # -----------------------------
                    WEBHOOK_URL = os.getenv("N8N_WEBHOOK")
                    if not WEBHOOK_URL:
                        print("[!] WARNING: N8N_WEBHOOK environment variable not found.")
                    else:
                        print(f"[*] Sending {len(df)} records to Webhook...")
                        for i, row_data in df.iterrows():
                            try:
                                r = requests.post(WEBHOOK_URL, json=row_data.to_dict(), timeout=30)
                                if (i + 1) % 10 == 0 or (i + 1) == len(df):
                                    print(f"[*] Progress: {i+1}/{len(df)} (Last Status: {r.status_code})")
                                time.sleep(0.5)
                            except Exception as e:
                                print(f"[!] Webhook Error at record {i}: {e}")

                    print("✅ ALL TASKS COMPLETED SUCCESSFULLY")
                    mailbox.stop()

                except Exception as e:
                    print(f"[ERROR inside on_message] {e}")

        mailbox.start(on_message, interval=5)
        
        # Keep the script alive for the email listener to finish
        print("[*] Script sleeping for 180s to allow async tasks to finish...")
        time.sleep(180)

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")

    finally:
        print("[*] Closing Browser.")
        driver.quit()

if __name__ == "__main__":
    run_full_automation()
