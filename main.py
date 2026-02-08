
# =========================================
# MLSU FULL NAVIGATION TEST BOT (ROBUST)
# =========================================

import os
import time
import threading
import logging

from flask import Flask

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException


# =========================================
# CONFIG
# =========================================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"

HOME_URL = "https://mlsuexamination.sumsraj.com/default.aspx"

WAIT_TIME = 45


# =========================================
# LOGGING
# =========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================================
# FLASK (KEEP RENDER ALIVE)
# =========================================

app = Flask(__name__)


@app.route("/")
def home():
    return "MLSU Robust Test Bot Running"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================================
# SELENIUM SETUP
# =========================================

def get_driver():
    opt = Options()
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--window-size=1920,1080")
    opt.add_argument("--disable-blink-features=AutomationControlled")

    return webdriver.Chrome(options=opt)


# =========================================
# SAFE CLICK
# =========================================

def safe_click(driver, element, name="element"):

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(1)
        element.click()
        return True

    except ElementClickInterceptedException:

        logging.warning(f"{name} click intercepted. Using JS click.")

        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            logging.error(f"JS click failed on {name}: {e}")
            return False

    except Exception as e:

        logging.error(f"Click failed on {name}: {e}")
        return False


# =========================================
# NAVIGATION TEST
# =========================================

def run_navigation_test():

    driver = None

    try:

        driver = get_driver()
        wait = WebDriverWait(driver, WAIT_TIME)

        # STEP 1: Open Home
        logging.info("Opening homepage...")
        driver.get(HOME_URL)
        time.sleep(5)

        # STEP 2: Click Admit Card View Details
        logging.info("Finding Admit Card View Details...")

        admit_btn = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(.,'Admit Card')]//a[contains(text(),'View Details')]"
        )))

        if not safe_click(driver, admit_btn, "Admit View Details"):
            return False, "Failed to click Admit Card View Details"

        time.sleep(3)

        # STEP 3: Wait for Modal
        logging.info("Waiting for popup modal...")

        wait.until(EC.visibility_of_element_located((
            By.CLASS_NAME,
            "modal-content"
        )))

        time.sleep(2)

        # STEP 4: Click Semester Link
        logging.info("Finding Semester Examination link...")

        sem_link = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//a[contains(text(),'Semester')]"
        )))

        if not safe_click(driver, sem_link, "Semester Link"):
            return False, "Failed to click Semester link"

        time.sleep(5)

        # STEP 5: Wait for Course Table
        logging.info("Waiting for course table...")

        table = wait.until(EC.presence_of_element_located((
            By.TAG_NAME,
            "table"
        )))

        rows = table.find_elements(By.TAG_NAME, "tr")

        if len(rows) < 7:
            return False, f"Only {len(rows)} rows found (expected 7+)"

        # STEP 6: Click 7th Row
        logging.info("Selecting 7th course row...")

        row7 = rows[6]
        link = row7.find_element(By.TAG_NAME, "a")

        if not safe_click(driver, link, "7th Course Link"):
            return False, "Failed to click 7th course link"

        time.sleep(5)

        # STEP 7: Check Roll Form
        logging.info("Checking roll form...")

        wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//input[@type='text']"
        )))

        wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//input[contains(@id,'Roll') or contains(@id,'roll')]"
        )))

        return True, "Navigation completed. Roll form reached."


    except Exception as e:

        logging.error("Navigation failed", exc_info=True)
        return False, str(e)


    finally:

        if driver:
            driver.quit()


# =========================================
# TELEGRAM COMMAND
# =========================================

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("🔍 Running robust navigation test...")

    ok, msg = run_navigation_test()

    if ok:
        await update.message.reply_text(f"✅ SUCCESS\n\n{msg}")
    else:
        await update.message.reply_text(f"❌ FAILED\n\n{msg}")


# =========================================
# BOT
# =========================================

def main():

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("test", test))

    logging.info("Robust test bot started")

    bot_app.run_polling()


# =========================================
# MAIN
# =========================================

if __name__ == "__main__":

    threading.Thread(target=run_flask, daemon=True).start()

    main()

