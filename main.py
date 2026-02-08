# =========================================
# MLSU ROBUST NAVIGATION TEST BOT
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

WAIT_TIME = 50


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
    opt.add_argument("--disable-blink-features=AutomationControlled")

    return webdriver.Chrome(options=opt)


# =========================================
# SAFE CLICK FUNCTION
# =========================================

def safe_click(driver, element, name="element"):

    try:

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            element
        )

        time.sleep(1)

        element.click()

        return True


    except ElementClickInterceptedException:

        logging.warning(f"{name} click intercepted, using JS click")

        try:

            driver.execute_script(
                "arguments[0].click();",
                element
            )

            return True

        except Exception as e:

            logging.error(f"JS click failed on {name}: {e}")

            return False


    except Exception as e:

        logging.error(f"Click failed on {name}: {e}")

        return False


# =========================================
# MAIN NAVIGATION TEST
# =========================================

def run_navigation_test():

    driver = None

    try:

        driver = get_driver()
        wait = WebDriverWait(driver, WAIT_TIME)

        # STEP 1: Open Homepage
        logging.info("Opening homepage...")

        driver.get(HOME_URL)

        time.sleep(6)


        # STEP 2: Click Admit Card → View Details
        logging.info("Finding Admit Card View Details...")

        admit_btn = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(.,'Admit Card')]//a[contains(text(),'View Details')]"
        )))

        if not safe_click(driver, admit_btn, "Admit View Details"):

            return False, "Failed to click Admit Card View Details"

        time.sleep(4)


        # STEP 3: Wait for Modal
        logging.info("Waiting for popup modal...")

        wait.until(EC.visibility_of_element_located((
            By.CLASS_NAME,
            "modal-content"
        )))

        time.sleep(2)


        # STEP 4: Click Semester Link
        logging.info("Finding Semester link...")

        sem_link = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//a[contains(text(),'Semester')]"
        )))

        if not safe_click(driver, sem_link, "Semester Link"):

            return False, "Failed to click Semester link"

        time.sleep(6)


        # STEP 5: Wait for course rows (with retry)
        logging.info("Waiting for course rows (with retry)...")

        max_retries = 3
        rows = []

        for attempt in range(max_retries):

            try:

                wait.until(lambda d: len(
                    d.find_elements(By.XPATH, "//table//tr")
                ) >= 8)

                rows = driver.find_elements(By.XPATH, "//table//tr")

                if len(rows) >= 8:

                    logging.info(f"Rows loaded on attempt {attempt+1}")

                    break

            except Exception:

                logging.warning(f"Rows not loaded. Retry {attempt+1}/{max_retries}")

                driver.refresh()

                time.sleep(6)

        else:

            return False, "Course list not loading. Possibly blocked by server."


        # STEP 6: Find B.Sc Row (Smart + Fallback)

        try:

            logging.info("Searching B.Sc row by text...")

            bsc_row = driver.find_element(
                By.XPATH,
                "//tr[td[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'B.SC')]]"
            )

            logging.info("B.Sc row found by text")


        except Exception:

            logging.warning("Text search failed. Using index fallback...")

            if len(rows) < 8:
                return False, "Not enough rows for fallback"

            bsc_row = rows[7]

            logging.info("B.Sc row selected by index")


        # STEP 7: Click B.Sc "Click Here"

        bsc_link = bsc_row.find_element(
            By.XPATH,
            ".//a[contains(text(),'Click')]"
        )

        logging.info("Clicking B.Sc link...")

        if not safe_click(driver, bsc_link, "B.Sc Link"):

            return False, "Failed to click B.Sc link"

        time.sleep(6)


        # STEP 8: Check Roll Form

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

    await update.message.reply_text(
        "⏳ Running testing, please wait..."
    )

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

    logging.info("Navigation test bot started")

    bot_app.run_polling()


# =========================================
# MAIN
# =========================================

if __name__ == "__main__":

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    main()
