
import os
import time
import sqlite3
import threading

from flask import Flask

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import pdfplumber
from pdf2image import convert_from_path


# =========================
# CONFIG
# =========================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"
ADMIN_ID = 8343668073

URL = "https://mlsuexamination.sumsraj.com/"

DATA_DIR = "data"
DB_FILE = "students.db"


# =========================

os.makedirs(DATA_DIR, exist_ok=True)


# =========================
# DATABASE
# =========================

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS students(
    roll TEXT PRIMARY KEY,
    name TEXT,
    image TEXT,
    blocked INTEGER DEFAULT 0
)
""")

conn.commit()


# =========================
# SELENIUM
# =========================

opt = Options()
opt.add_argument("--headless=new")
opt.add_argument("--no-sandbox")
opt.add_argument("--disable-dev-shm-usage")

prefs = {
    "download.default_directory": os.path.abspath(DATA_DIR),
    "download.prompt_for_download": False
}

opt.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(options=opt)
wait = WebDriverWait(driver, 20)

driver.get(URL)


# =========================
# HELPERS
# =========================

def latest_pdf():

    files = os.listdir(DATA_DIR)
    pdfs = [f for f in files if f.endswith(".pdf")]

    if not pdfs:
        return None

    full = [os.path.join(DATA_DIR, f) for f in pdfs]
    return max(full, key=os.path.getctime)


def extract_name(pdf):

    try:
        with pdfplumber.open(pdf) as f:
            text = f.pages[0].extract_text()

        for line in text.split("\\n"):
            if "Name" in line:
                return line.split(":")[-1].strip()

    except:
        pass

    return "Unknown"


# =========================
# NAVIGATION
# =========================

def go_to_roll_page():

    driver.get(URL)

    sem = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        "//h3[contains(text(),'Semester Examination Form')]/../..//a"
    )))
    sem.click()

    wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))

    links = driver.find_elements(By.LINK_TEXT, "Click here")
    links[6].click()

    time.sleep(3)


# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.first_name

    msg = f"""
✨━━━━━━━━━━━━━━━━✨
🤖 WELCOME {user.upper()}
✨━━━━━━━━━━━━━━━━✨

📚 Admit Card Bot

🔍 /find Name
📥 /collect start end
🚫 /block roll
✅ /unblock roll

Good Luck 🍀
"""

    await update.message.reply_text(msg)


# =========================
# COLLECT
# =========================

async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admin only.")
        return

    try:
        s = int(context.args[0])
        e = int(context.args[1])
    except:
        await update.message.reply_text("/collect 230001 230050")
        return


    await update.message.reply_text("📥 Collecting...")

    go_to_roll_page()


    for roll in range(s, e+1):

        try:

            wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//input[contains(@id,'Roll')]"
            ))).click()

            box = driver.find_element(By.XPATH, "//input[@type='text']")
            box.clear()
            box.send_keys(str(roll))

            driver.find_element(By.XPATH, "//input[@type='submit']").click()

            time.sleep(6)


            pdf = latest_pdf()

            if not pdf:
                continue


            name = extract_name(pdf)

            images = convert_from_path(pdf)

            img = f"{DATA_DIR}/{roll}.jpg"
            images[0].save(img, "JPEG")

            os.remove(pdf)


            cur.execute("""
            INSERT OR REPLACE INTO students
            VALUES (?,?,?,0)
            """, (str(roll), name, img))

            conn.commit()


            await update.message.reply_text(
                f"✅ {roll} - {name}"
            )


        except:
            await update.message.reply_text(f"⚠️ Failed {roll}")


    await update.message.reply_text("🎉 Done!")


# =========================
# FIND
# =========================

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    name = " ".join(context.args)

    if not name:
        await update.message.reply_text("/find Rahul")
        return


    alert = f"""
🔔 SEARCH ALERT

User: @{user.username}
ID: {user.id}

Search: {name}
"""

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=alert
        )
    except:
        pass


    cur.execute("""
    SELECT image,roll,name,blocked
    FROM students
    WHERE name LIKE ?
    """, (f"%{name}%",))

    row = cur.fetchone()


    if not row:
        await update.message.reply_text("❌ Not found")
        return


    img, roll, real, blocked = row


    if blocked == 1:
        await update.message.reply_text("🚫 This record is restricted.")
        return


    await update.message.reply_photo(
        photo=open(img, "rb"),
        caption=f"{real}\\nRoll: {roll}"
    )


# =========================
# BLOCK
# =========================

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admin only.")
        return


    if not context.args:
        await update.message.reply_text("/block 8098")
        return


    roll = context.args[0]

    cur.execute("""
    UPDATE students
    SET blocked = 1
    WHERE roll = ?
    """, (roll,))

    conn.commit()


    if cur.rowcount == 0:
        await update.message.reply_text("❌ Roll not found.")
    else:
        await update.message.reply_text(f"✅ {roll} BLOCKED.")


# =========================
# UNBLOCK
# =========================

async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admin only.")
        return


    if not context.args:
        await update.message.reply_text("/unblock 8098")
        return


    roll = context.args[0]

    cur.execute("""
    UPDATE students
    SET blocked = 0
    WHERE roll = ?
    """, (roll,))

    conn.commit()


    if cur.rowcount == 0:
        await update.message.reply_text("❌ Roll not found.")
    else:
        await update.message.reply_text(f"✅ {roll} UNBLOCKED.")


# =========================
# FLASK (FOR RENDER)
# =========================

app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "🤖 Bot is Running!"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)


# =========================
# BOT
# =========================

def run_bot():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("collect", collect))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))

    print("🤖 Bot Running...")

    app.run_polling()


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    t = threading.Thread(target=run_flask)
    t.start()

    run_bot()
