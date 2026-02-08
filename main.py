
# ===============================
# MLSU NAVIGATION TEST BOT (FIXED)
# ===============================

import os
import time
import threading

from flask import Flask

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ===============================
# CONFIG
# ===============================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"

FORM_URL = "https://mlsuexamination.sumsraj.com/Exam_ForALL_AdmitCard.aspx?id=S"


# ===============================
# FLASK (KEEP RENDER ALIVE)
# ===============================

app = Flask(__name__)

@app.route("/")
def home():
    return "Test Bot Running"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ===============================
# SELENIUM SETUP
# ===============================

opt = Options()
opt.add_argument("--headless=new")
opt.add_argument("--no-sandbox")
opt.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=opt)
wait = WebDriverWait(driver, 40)


# ===============================
# TEST FUNCTION
# ===============================

def test_navigation():

    try:

        driver.get(FORM_URL)
        time.sleep(5)


        # Check redirect
        if "default" in driver.current_url.lower():
            return False, "Redirected to homepage"


        # Check roll option
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[contains(@id,'Roll')]"
        )))


        # Check input box
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[@type='text']"
        )))


        return True, "Navigation OK. Roll form detected."


    except Exception as e:

        return False, str(e)


# ===============================
# COMMAND
# ===============================

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("🔍 Testing navigation...")

    ok, msg = test_navigation()

    if ok:
        await update.message.reply_text(f"✅ SUCCESS\n{msg}")
    else:
        await update.message.reply_text(f"❌ FAILED\n{msg}")


# ===============================
# BOT
# ===============================

def main():

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("test", test))

    print("🤖 Test Bot Running...")

    app_bot.run_polling()


# ===============================
# MAIN
# ===============================

if __name__ == "__main__":

    # Start Flask for Render
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    main()

