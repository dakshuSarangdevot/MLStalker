
import os
import time
import sqlite3
import threading
import traceback

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

FORM_URL = "https://mlsuexamination.sumsraj.com/Exam_ForALL_AdmitCard.aspx?id=S"

DATA_DIR = "data"
DB_FILE = "students.db"
STATE_FILE = "state.txt"

MAX_BATCH = 100
MAX_RETRY = 3


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
# STATE (RESUME)
# =========================

def save_state(roll):
    with open(STATE_FILE, "w") as f:
        f.write(str(roll))


def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE) as f:
        return int(f.read().strip())


def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


# =========================
# SELENIUM
# =========================

opt = Options()
opt.add_argument("--headless=new")
opt.add_argument("--no-sandbox")
opt.add_argument("--disable-dev-shm-usage")
opt.add_argument("--disable-blink-features=AutomationControlled")

prefs = {
    "download.default_directory": os.path.abspath(DATA_DIR),
    "download.prompt_for_download": False
}

opt.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(options=opt)
wait = WebDriverWait(driver, 50)


# =========================
# HELPERS
# =========================

def latest_pdf():

    pdfs = [f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")]

    if not pdfs:
        return None

    paths = [os.path.join(DATA_DIR, f) for f in pdfs]
    return max(paths, key=os.path.getctime)


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

def open_form():

    driver.get(FORM_URL)
    time.sleep(4)

    if "default.aspx" in driver.current_url.lower():
        raise Exception("Redirected to homepage")

    wait.until(EC.presence_of_element_located((
        By.XPATH, "//input[contains(@id,'Roll')]"
    )))

    wait.until(EC.presence_of_element_located((
        By.XPATH, "//input[@type='text']"
    )))


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = update.effective_user.first_name

    msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 MLSU ADMIT CARD BOT (PRO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Welcome, {name}!

This bot collects, stores, and
manages MLSU admit cards.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📘 COMMAND GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 USERS
/find <name>    → Search
/stats          → Records

👑 ADMIN
/collect s e    → Collect
/retry          → Retry failed
/resume         → Resume last
/clearstate     → Reset resume
/block <roll>
/unblock <roll>
/cleardb
/admstats

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ FEATURES

✔ Auto resume
✔ Retry system
✔ Crash recovery
✔ Progress %
✔ Error alerts

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    await update.message.reply_text(msg)


# =========================
# COLLECT
# =========================

FAILED = []


async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Admin only.")
        return

    try:
        s = int(context.args[0])
        e = int(context.args[1])
    except:
        await update.message.reply_text("❌ /collect 230001 230050")
        return


    if e - s + 1 > MAX_BATCH:
        await update.message.reply_text(f"❌ Max {MAX_BATCH} allowed.")
        return


    await update.message.reply_text("📥 Collection started...")

    threading.Thread(
        target=run_collect,
        args=(update, context, s, e),
        daemon=True
    ).start()


def run_collect(update, context, s, e):

    global FAILED
    FAILED.clear()

    try:

        open_form()


        total = e - s + 1
        done = 0

        start_roll = load_state() or s


        if start_roll > s:
            context.application.create_task(
                update.message.reply_text(
                    f"🔁 Resuming from {start_roll}"
                )
            )


        for roll in range(start_roll, e+1):

            save_state(roll)


            success = False


            for attempt in range(1, MAX_RETRY+1):

                try:

                    context.application.create_task(
                        update.message.reply_text(
                            f"⏳ {roll} | Try {attempt}"
                        )
                    )


                    driver.find_element(
                        By.XPATH,
                        "//input[contains(@id,'Roll')]"
                    ).click()


                    box = driver.find_element(
                        By.XPATH,
                        "//input[@type='text']"
                    )
                    box.clear()
                    box.send_keys(str(roll))


                    driver.find_element(
                        By.XPATH,
                        "//input[@type='submit']"
                    ).click()

                    time.sleep(4)


                    pdf = latest_pdf()

                    if not pdf:
                        raise Exception("PDF not downloaded")


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
                    percent = int((done/total)*100)


                    context.application.create_task(
                        update.message.reply_text(
                            f"✅ {done}/{total} ({percent}%) | {roll}"
                        )
                    )


                    success = True
                    break


                except Exception as er:

                    context.application.create_task(
                        update.message.reply_text(
                            f"⚠️ {roll} Failed ({attempt}): {er}"
                        )
                    )

                    time.sleep(2)


            if not success:

                FAILED.append(roll)

                context.application.create_task(
                    update.message.reply_text(
                        f"❌ {roll} Skipped after retries"
                    )
                )


        clear_state()


        context.application.create_task(
            update.message.reply_text(
                f"🎉 Done. Failed: {len(FAILED)}"
            )
        )


    except Exception as e:

        err = traceback.format_exc()

        context.application.create_task(
            update.message.reply_text(
                f"🔥 CRITICAL:\n{err[:350]}"
            )
        )


# =========================
# RETRY FAILED
# =========================

async def retry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    if not FAILED:
        await update.message.reply_text("✅ No failed rolls.")
        return

    await update.message.reply_text(f"🔁 Retrying {len(FAILED)} rolls")

    threading.Thread(
        target=retry_failed,
        args=(update, context),
        daemon=True
    ).start()


def retry_failed(update, context):

    global FAILED

    failed_copy = FAILED.copy()
    FAILED.clear()

    for roll in failed_copy:

        try:

            open_form()


            driver.find_element(
                By.XPATH,
                "//input[contains(@id,'Roll')]"
            ).click()


            box = driver.find_element(
                By.XPATH,
                "//input[@type='text']"
            )
            box.clear()
            box.send_keys(str(roll))


            driver.find_element(
                By.XPATH,
                "//input[@type='submit']"
            ).click()

            time.sleep(4)


            pdf = latest_pdf()

            if not pdf:
                raise Exception("PDF missing")


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


            context.application.create_task(
                update.message.reply_text(
                    f"✅ Retried {roll}"
                )
            )


        except Exception as e:

            context.application.create_task(
                update.message.reply_text(
                    f"❌ Retry failed {roll}"
                )
            )


# =========================
# RESUME / CLEAR
# =========================

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    pos = load_state()

    if not pos:
        await update.message.reply_text("✅ Nothing to resume.")
        return

    await update.message.reply_text(
        f"🔁 Resume available from {pos}"
    )


async def clearstate(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    clear_state()
    await update.message.reply_text("🗑️ Resume state cleared.")


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
        await update.message.reply_text("❌ No record found.")
        return


    img, roll, real, blocked = row


    if blocked == 1:
        await update.message.reply_text("🚫 Blocked by admin.")
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

    await update.message.reply_text(f"📊 Total: {total}")


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

Total   : {total}
Blocked : {blocked}
Batch   : {MAX_BATCH}
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
    return "🤖 MLSU Bot Running"


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
    app.add_handler(CommandHandler("retry", retry))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("clearstate", clearstate))
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
