
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

MAX_BATCH = 100


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
# START COMMAND
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = update.effective_user.first_name

    msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖  MLSU ADMIT CARD BOT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👋 Welcome, {name}!

This bot helps you instantly find
and download MLSU admit cards.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 HOW TO USE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ Type:
   /find Rahul Sharma

2️⃣ Bot will search database

3️⃣ If found → Admit Card sent

⚡ Fast • Secure • 24/7

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 USER COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 /find <name>   → Search admit card
📊 /stats         → Total records

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👑 ADMIN COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📥 /collect s e   → Download data
🚫 /block roll    → Block record
✅ /unblock roll  → Unblock record
🗑️ /cleardb       → Delete database
📊 /admstats      → Admin stats

(Max Batch: {MAX_BATCH})

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Tip:
Search by partial name if full
name doesn't match.

Example:
/find Sharma

Best of Luck for Exams 🍀📚
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    await update.message.reply_text(msg)


# =========================
# COLLECT
# =========================

async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admin only command.")
        return

    try:
        s = int(context.args[0])
        e = int(context.args[1])
    except:
        await update.message.reply_text("❌ /collect 230001 230050")
        return


    if e - s + 1 > MAX_BATCH:
        await update.message.reply_text(
            f"❌ Max {MAX_BATCH} rolls allowed."
        )
        return


    await update.message.reply_text("📥 Collection started...")

    threading.Thread(
        target=run_collect,
        args=(update, context, s, e),
        daemon=True
    ).start()


def run_collect(update, context, s, e):

    go_to_roll_page()

    total = e - s + 1
    done = 0


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

            time.sleep(4)


            pdf = latest_pdf()

            if not pdf:
                continue


            name = extract_name(pdf)

            images = convert_from_path(pdf, dpi=120)

            img = f"{DATA_DIR}/{roll}.jpg"
            images[0].save(img, "JPEG", quality=70)

            os.remove(pdf)


            cur.execute("""
            INSERT OR REPLACE INTO students
            VALUES (?,?,?,0)
            """, (str(roll), name, img))

            conn.commit()


            done += 1


            if done % 5 == 0 or done == total:

                context.application.create_task(
                    update.message.reply_text(
                        f"✅ Progress: {done}/{total}"
                    )
                )


        except:

            context.application.create_task(
                update.message.reply_text(f"⚠️ Failed {roll}")
            )


    context.application.create_task(
        update.message.reply_text("🎉 Collection Completed!")
    )


# =========================
# FIND
# =========================

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = " ".join(context.args)

    if not name:
        await update.message.reply_text("❌ /find Rahul")
        return


    cur.execute("""
    SELECT image,roll,name,blocked
    FROM students
    WHERE name LIKE ?
    """, (f"%{name}%",))

    row = cur.fetchone()


    if not row:
        await update.message.reply_text("❌ Record not found.")
        return


    img, roll, real, blocked = row


    if blocked == 1:
        await update.message.reply_text("🚫 This record is restricted.")
        return


    await update.message.reply_photo(
        photo=open(img, "rb"),
        caption=f"{real}\nRoll: {roll}"
    )


# =========================
# STATS
# =========================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cur.execute("SELECT COUNT(*) FROM students")
    total = cur.fetchone()[0]

    await update.message.reply_text(
        f"📊 Total Records: {total}"
    )


# =========================
# ADMIN STATS
# =========================

async def admstats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM students")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM students WHERE blocked=1")
    blocked = cur.fetchone()[0]

    msg = f"""
👑 ADMIN REPORT

📄 Total Records : {total}
🚫 Blocked       : {blocked}
⚡ Batch Limit   : {MAX_BATCH}
"""

    await update.message.reply_text(msg)


# =========================
# CLEAR DB
# =========================

async def cleardb(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("DELETE FROM students")
    conn.commit()

    await update.message.reply_text("🗑️ Database cleared.")


# =========================
# BLOCK / UNBLOCK
# =========================

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    roll = context.args[0]

    cur.execute("UPDATE students SET blocked=1 WHERE roll=?", (roll,))
    conn.commit()

    await update.message.reply_text(f"🚫 {roll} BLOCKED")


async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    roll = context.args[0]

    cur.execute("UPDATE students SET blocked=0 WHERE roll=?", (roll,))
    conn.commit()

    await update.message.reply_text(f"✅ {roll} UNBLOCKED")


# =========================
# FLASK
# =========================

app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "🤖 MLSU Bot Running Successfully!"


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
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("admstats", admstats))
    app.add_handler(CommandHandler("cleardb", cleardb))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))

    print("🤖 Bot Running...")

    app.run_polling()


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    threading.Thread(target=run_flask, daemon=True).start()

    run_bot()
