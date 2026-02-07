
# ===============================
# MLSU BOT - FINAL STABLE VERSION
# ===============================

import os, time, threading, sqlite3, traceback

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


# ===============================
# CONFIG
# ===============================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"
SUPER_ADMIN = 8343668073

FORM_URL = "https://mlsuexamination.sumsraj.com/Exam_ForALL_AdmitCard.aspx?id=S"

DATA_DIR = "data"
DB_FILE = "students.db"
ADMIN_DB = "admins.db"

MAX_BATCH = 100
MAX_RETRY = 3


# ===============================

os.makedirs(DATA_DIR, exist_ok=True)


# ===============================
# DATABASES
# ===============================

# Students DB
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


# Admin DB
acon = sqlite3.connect(ADMIN_DB, check_same_thread=False)
acur = acon.cursor()

acur.execute("""
CREATE TABLE IF NOT EXISTS admins(
 id INTEGER PRIMARY KEY
)
""")

# Insert super admin
acur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (SUPER_ADMIN,))
acon.commit()


# ===============================
# ADMIN HELPERS
# ===============================

def is_admin(uid):
    acur.execute("SELECT 1 FROM admins WHERE id=?", (uid,))
    return acur.fetchone() is not None


def add_admin(uid):
    acur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (uid,))
    acon.commit()


def remove_admin(uid):
    if uid == SUPER_ADMIN:
        return False

    acur.execute("DELETE FROM admins WHERE id=?", (uid,))
    acon.commit()
    return True


def list_admins():
    acur.execute("SELECT id FROM admins")
    return [i[0] for i in acur.fetchall()]


# ===============================
# SELENIUM
# ===============================

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
wait = WebDriverWait(driver, 40)


# ===============================
# HELPERS
# ===============================

def latest_pdf():
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")]
    if not files:
        return None

    paths = [os.path.join(DATA_DIR, f) for f in files]
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


def open_form():

    driver.get(FORM_URL)
    time.sleep(4)

    if "default" in driver.current_url.lower():
        raise Exception("Redirected to homepage")

    wait.until(EC.presence_of_element_located((
        By.XPATH, "//input[contains(@id,'Roll')]"
    )))


# ===============================
# START
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = """
━━━━━━━━━━━━━━━━━━━━━━
🤖 MLSU BOT (STABLE)
━━━━━━━━━━━━━━━━━━━━━━

👤 USER
/find <name>
/stats

👑 ADMIN
/collect s e
/makeadmin <id>
/removeadmin <id>
/adminlist
/block <roll>
/unblock <roll>

⚙ FEATURES
✔ Multi Admin
✔ % Progress
✔ Error Logs
✔ Stable

━━━━━━━━━━━━━━━━━━━━━━
"""

    await update.message.reply_text(msg)


# ===============================
# ADMIN COMMANDS
# ===============================

async def makeadmin(update, context):

    if update.effective_user.id != SUPER_ADMIN:
        await update.message.reply_text("🚫 Only owner can add admins")
        return

    try:
        uid = int(context.args[0])
    except:
        await update.message.reply_text("/makeadmin <id>")
        return

    add_admin(uid)

    await update.message.reply_text(f"✅ {uid} is now admin")


async def removeadmin(update, context):

    if update.effective_user.id != SUPER_ADMIN:
        return

    try:
        uid = int(context.args[0])
    except:
        return

    if remove_admin(uid):
        await update.message.reply_text("✅ Removed")
    else:
        await update.message.reply_text("❌ Cannot remove owner")


async def adminlist(update, context):

    if not is_admin(update.effective_user.id):
        return

    admins = list_admins()

    txt = "👑 ADMINS:\n" + "\n".join(map(str, admins))

    await update.message.reply_text(txt)


# ===============================
# COLLECT
# ===============================

async def collect(update, context):

    uid = update.effective_user.id

    if not is_admin(uid):
        await update.message.reply_text("🚫 Admin only")
        return

    try:
        s = int(context.args[0])
        e = int(context.args[1])
    except:
        await update.message.reply_text("/collect 230001 230050")
        return

    if e - s + 1 > MAX_BATCH:
        await update.message.reply_text("❌ Batch too large")
        return

    await update.message.reply_text("📥 Collection started")

    threading.Thread(
        target=run_collect,
        args=(context.application, update.effective_chat.id, s, e),
        daemon=True
    ).start()


def run_collect(app, chat, s, e):

    try:

        open_form()

        total = e - s + 1
        done = 0
        last_percent = -1

        for roll in range(s, e+1):

            success = False

            for attempt in range(1, MAX_RETRY+1):

                try:

                    driver.find_element(
                        By.XPATH, "//input[contains(@id,'Roll')]"
                    ).click()

                    box = driver.find_element(
                        By.XPATH, "//input[@type='text']"
                    )

                    box.clear()
                    box.send_keys(str(roll))

                    driver.find_element(
                        By.XPATH, "//input[@type='submit']"
                    ).click()

                    time.sleep(4)

                    pdf = latest_pdf()

                    if not pdf:
                        raise Exception("PDF not found")


                    name = extract_name(pdf)

                    images = convert_from_path(pdf, dpi=110)

                    img = f"{DATA_DIR}/{roll}.jpg"
                    images[0].save(img, "JPEG", quality=70)

                    os.remove(pdf)


                    cur.execute("""
                    INSERT OR REPLACE INTO students
                    VALUES (?,?,?,0)
                    """, (roll, name, img))

                    conn.commit()


                    done += 1
                    percent = int((done/total)*100)


                    if done % 5 == 0 or percent != last_percent:

                        app.bot.send_message(
                            chat_id=chat,
                            text=f"📊 {done}/{total} ({percent}%)"
                        )

                        last_percent = percent


                    success = True
                    break


                except Exception as er:

                    if attempt == MAX_RETRY:

                        app.bot.send_message(
                            chat_id=chat,
                            text=f"❌ {roll} Failed: {er}"
                        )

                    time.sleep(2)


            if not success:
                continue


        app.bot.send_message(
            chat_id=chat,
            text="✅ Collection completed"
        )


    except Exception as e:

        app.bot.send_message(
            chat_id=chat,
            text=f"🔥 ERROR:\n{str(e)}"
        )


# ===============================
# BLOCK / UNBLOCK
# ===============================

async def block(update, context):

    if not is_admin(update.effective_user.id):
        return

    roll = context.args[0]

    cur.execute("UPDATE students SET blocked=1 WHERE roll=?", (roll,))
    conn.commit()

    await update.message.reply_text("🚫 Blocked")


async def unblock(update, context):

    if not is_admin(update.effective_user.id):
        return

    roll = context.args[0]

    cur.execute("UPDATE students SET blocked=0 WHERE roll=?", (roll,))
    conn.commit()

    await update.message.reply_text("✅ Unblocked")


# ===============================
# FIND / STATS
# ===============================

async def find(update, context):

    name = " ".join(context.args)

    if not name:
        return

    cur.execute("""
    SELECT image,roll,name,blocked
    FROM students
    WHERE name LIKE ?
    """, (f"%{name}%",))

    r = cur.fetchone()

    if not r:
        await update.message.reply_text("❌ Not found")
        return

    img, roll, nm, blk = r

    if blk:
        await update.message.reply_text("🚫 Blocked")
        return

    await update.message.reply_photo(
        open(img, "rb"),
        caption=f"{nm}\nRoll: {roll}"
    )


async def stats(update, context):

    cur.execute("SELECT COUNT(*) FROM students")

    await update.message.reply_text(
        f"📊 Total: {cur.fetchone()[0]}"
    )


# ===============================
# FLASK
# ===============================

appf = Flask(__name__)


@appf.route("/")
def home():
    return "Bot Running"


def run_flask():
    p = int(os.environ.get("PORT", 10000))
    appf.run(host="0.0.0.0", port=p)


# ===============================
# BOT
# ===============================

def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("makeadmin", makeadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("adminlist", adminlist))

    app.add_handler(CommandHandler("collect", collect))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))

    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stats", stats))

    print("🤖 BOT RUNNING")

    app.run_polling()


# ===============================
# MAIN
# ===============================

if __name__ == "__main__":

    threading.Thread(target=run_flask, daemon=True).start()

    main()

