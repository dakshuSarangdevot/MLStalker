
# =========================================
# MLSU FULL NAVIGATION TEST BOT
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


# =========================================
# CONFIG
# =========================================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"

HOME_URL = "https://mlsuexamination.sumsraj.com/default.aspx"

WAIT_TIME = 40


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
    return "MLSU Test Bot Running"


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

    return webdriver.Chrome(options=opt)


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

        # STEP 2: Click Admit Card -> View Details
        logging.info("Clicking Admit Card View Details...")

        admit_btn = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(.,'Admit Card')]//a[contains(text(),'View Details')]"
        )))

        admit_btn.click()
        time.sleep(3)

        # STEP 3: Wait for Modal
        logging.info("Waiting for popup modal...")

        modal = wait.until(EC.visibility_of_element_located((
            By.CLASS_NAME,
            "modal-content"
        )))

        time.sleep(2)

        # STEP 4: Click Semester Link
        logging.info("Clicking Semester Examination link...")

        sem_link = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//a[contains(text(),'Semester')]"
        )))

        sem_link.click()
        time.sleep(5)

        # STEP 5: Wait for Course Table
        logging.info("Waiting for course list...")

        table = wait.until(EC.presence_of_element_located((
            By.TAG_NAME,
            "table"
        )))

        rows = table.find_elements(By.TAG_NAME, "tr")

        if len(rows) < 7:
            return False, f"Only {len(rows)} rows found. Expected 7+"

        # STEP 6: Click 7th Row Link
        logging.info("Clicking 7th course row...")

        row7 = rows[6]
        link = row7.find_element(By.TAG_NAME, "a")
        link.click()

        time.sleep(5)

        # STEP 7: Check Roll Input
        logging.info("Checking roll number form...")

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

    await update.message.reply_text("🔍 Starting full navigation test...")

    ok, msg = run_navigation_test()

    if ok:

        await update.message.reply_text(
            f"✅ SUCCESS\n\n{msg}"
        )

    else:

        await update.message.reply_text(
            f"❌ FAILED\n\n{msg}"
        )


# =========================================
# BOT
# =========================================

def main():

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("test", test))

    logging.info("Test bot started")

    bot_app.run_polling()


# =========================================
# MAIN
# =========================================

if __name__ == "__main__":

    threading.Thread(target=run_flask, daemon=True).start()

    main()

