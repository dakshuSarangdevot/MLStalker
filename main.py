
# ===============================
# MLSU NAVIGATION TEST BOT
# ===============================

import time
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
        time.sleep(4)


        # Check redirect
        if "default" in driver.current_url.lower():
            return False, "Redirected to homepage"


        # Check roll radio
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[contains(@id,'Roll')]"
        )))


        # Check input box
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[@type='text']"
        )))


        return True, "Navigation OK. Form detected."


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

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("test", test))

    print("🤖 Test Bot Running...")

    app.run_polling()


# ===============================
# MAIN
# ===============================

if __name__ == "__main__":

    main()
