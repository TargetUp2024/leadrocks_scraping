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
start_date = datetime(2026, 3, 23)
base_value = 50
today = datetime.now()
days_passed = (today - start_date).days

a = base_value + (days_passed * 50)

page = (a // 500) + 1
start_in_page = a % 500
end_in_page = start_in_page + 50


# -----------------------------
# CHROME OPTIONS (CI SAFE)
# -----------------------------
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")  # required for GitHub Actions
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
)

service = Service(ChromeDriverManager().install())


# -----------------------------
# MAIN FUNCTION
# -----------------------------
def run_full_automation():
    mailbox = Email()
    mailbox.register()
    email_addr = mailbox.address

    print(f"[*] Generated Email: {email_addr}")

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 30)

    try:
        print("[*] Navigating to Login...")
        driver.get("https://leadrocks.io/login")

        email_input = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type=email]"))
        )
        email_input.send_keys(email_addr)

        driver.find_element(
            By.XPATH, "//button[contains(text(), 'Next')]"
        ).click()

        print("[*] Waiting for PIN...")

        # -----------------------------
        # EMAIL LISTENER (UNCHANGED LOGIC)
        # -----------------------------
        def on_message(message):
            print("\n[!] Email received")

            match = re.search(r"\b\d{5}\b", message["text"])

            if match:
                pin_code = match.group()
                print(f"[PIN] {pin_code}")

                try:
                    pin_field = wait.until(
                        EC.element_to_be_clickable((By.NAME, "pin"))
                    )
                    pin_field.send_keys(pin_code)

                    # FIXED SELECTOR
                    driver.find_element(By.CSS_SELECTOR, "button.gobtn").click()

                    print("[*] Logged in")

                    time.sleep(5)

                    # -----------------------------
                    # NAVIGATION
                    # -----------------------------
                    url = f"https://leadrocks.io/my?position=morocco&pp=500&p={page}"
                    driver.get(url)

                    wait.until(
                        EC.presence_of_all_elements_located(
                            (By.CSS_SELECTOR, "td input[type='checkbox']")
                        )
                    )

                    checkboxes = driver.find_elements(
                        By.CSS_SELECTOR, "td input[type='checkbox']"
                    )

                    target_boxes = checkboxes[start_in_page:end_in_page]

                    checked = 0
                    for box in target_boxes:
                        try:
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", box
                            )
                            if not box.is_selected():
                                box.click()
                                checked += 1
                        except:
                            pass

                    print(f"[+] Selected {checked}")

                    # SAVE
                    save_btn = wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[normalize-space()='Open and save selected']")
                        )
                    )
                    save_btn.click()

                    list_btn = wait.until(
                        EC.element_to_be_clickable(
                            (
                                By.XPATH,
                                "//div[contains(@class,'leads-lists')]//button[normalize-space()='Default list']",
                            )
                        )
                    )
                    list_btn.click()

                    time.sleep(5)

                    # -----------------------------
                    # SCRAPE
                    # -----------------------------
                    driver.get("https://leadrocks.io/my/leads")

                    dropdown = wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, "per_page"))
                    )
                    Select(dropdown).select_by_value("500")

                    time.sleep(3)

                    rows = driver.find_elements(By.CSS_SELECTOR, "tr[data-id]")

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

                    print(f"[+] Extracted {len(df)} leads")

                    # -----------------------------
                    # WEBHOOK
                    # -----------------------------
                    WEBHOOK_URL = os.getenv("N8N_WEBHOOK")

                    for i, row in df.iterrows():
                        try:
                            r = requests.post(WEBHOOK_URL, json=row.to_dict(), timeout=30)
                            print(f"{i+1}/{len(df)} -> {r.status_code}")
                            time.sleep(1)
                        except Exception as e:
                            print("ERROR:", e)

                    print("✅ DONE")

                    mailbox.stop()

                except Exception as e:
                    print("[ERROR]", e)

        mailbox.start(on_message, interval=5)

        # prevent GitHub job from exiting immediately
        time.sleep(180)

    except Exception as e:
        print("[CRITICAL]", e)

    finally:
        driver.quit()


if __name__ == "__main__":
    run_full_automation()
