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
# CONFIG
# -----------------------------
WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

start_date = datetime(2026, 3, 23)
base_value = 50
today = datetime.now()
days_passed = (today - start_date).days

a = base_value + (days_passed * 50)

page = (a // 500) + 1
start_in_page = a % 500
end_in_page = start_in_page + 50


# -----------------------------
# BROWSER SETUP (CI SAFE)
# -----------------------------
def create_driver():
    options = webdriver.ChromeOptions()

    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    )

    service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(service=service, options=options)


# -----------------------------
# MAIN LOGIC
# -----------------------------
def run():
    driver = create_driver()
    wait = WebDriverWait(driver, 30)

    mailbox = Email()
    mailbox.register()
    email_addr = mailbox.address

    print(f"[EMAIL] {email_addr}")

    try:
        # -----------------------------
        # LOGIN
        # -----------------------------
        driver.get("https://leadrocks.io/login")

        email_input = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type=email]"))
        )
        email_input.send_keys(email_addr)

        driver.find_element(By.XPATH, "//button[contains(text(),'Next')]").click()

        print("[WAITING FOR PIN]")

        pin_code = wait_for_pin(mailbox, timeout=120)

        if not pin_code:
            raise Exception("PIN not received")

        print(f"[PIN] {pin_code}")

        pin_field = wait.until(
            EC.element_to_be_clickable((By.NAME, "pin"))
        )
        pin_field.send_keys(pin_code)

        driver.find_element(By.CSS_SELECTOR, "button.gobtn").click()

        time.sleep(5)

        # -----------------------------
        # NAVIGATE
        # -----------------------------
        url = f"https://leadrocks.io/my?pp=500&p={page}&position=morocco"
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

        for box in target_boxes:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", box
                )
                if not box.is_selected():
                    box.click()
            except:
                pass

        # -----------------------------
        # SAVE
        # -----------------------------
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

        # -----------------------------
        # SCRAPE
        # -----------------------------
        driver.get("https://leadrocks.io/my/leads")

        dropdown = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "per_page"))
        )
        Select(dropdown).select_by_value("500")

        time.sleep(3)

        df = extract_leads(driver)

        if df.empty:
            print("No leads found")
            return

        df["Country"] = "Maroc"

        send_to_webhook(df)

    finally:
        driver.quit()


# -----------------------------
# EMAIL HANDLING
# -----------------------------
def wait_for_pin(mailbox, timeout=120):
    start = time.time()

    while time.time() - start < timeout:
        messages = mailbox.get_messages()

        for msg in messages:
            content = mailbox.get_message(msg["id"])["text"]

            match = re.search(r"\b\d{5}\b", content)
            if match:
                return match.group()

        time.sleep(5)

    return None


# -----------------------------
# SCRAPING
# -----------------------------
def extract_leads(driver):
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
            })

        except:
            continue

    return pd.DataFrame(data)


# -----------------------------
# WEBHOOK
# -----------------------------
def send_to_webhook(df):
    for i, row in df.iterrows():
        payload = row.to_dict()

        try:
            r = requests.post(WEBHOOK_URL, json=payload, timeout=30)

            print(f"{i+1}/{len(df)} -> {r.status_code}")

            time.sleep(1)

        except Exception as e:
            print("ERROR:", e)


# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":
    run()
