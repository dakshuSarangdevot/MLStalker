import os
import re
import sqlite3
import logging
import tempfile
import asyncio

import pdfplumber

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIG =================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"
OWNER_ID = 8343668073

DB_FILE = "data.db"
MAX_QUEUE = 50

# =========================================

logging.basicConfig(level=logging.INFO)

# =============== DATABASE ================

def init_db():

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        roll TEXT PRIMARY KEY,
        name TEXT,
        file_id TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins(
        uid INTEGER UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS blocked(
        roll TEXT UNIQUE
    )
    """)

    cur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (OWNER_ID,))

    con.commit()
    con.close()


def db():
    return sqlite3.connect(DB_FILE)


# =============== HELPERS =================

def is_admin(uid):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT 1 FROM admins WHERE uid=?", (uid,))
    r = cur.fetchone()

    con.close()

    return r is not None


def is_blocked(roll):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT 1 FROM blocked WHERE roll=?", (roll,))
    r = cur.fetchone()

    con.close()

    return r is not None


def extract_pdf(path):

    try:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text()

        roll = re.search(r"Roll No\.\s*:\s*(\d+)", text)
        name = re.search(r"Candidate's Name\s*:\s*(.+)", text)

        if not roll or not name:
            return None, None

        return roll.group(1), name.group(1)

    except:
        return None, None


# =============== QUEUE ===================

queue = asyncio.Queue()


async def worker():

    while True:

        update, context, file_id = await queue.get()

        try:

            file = await context.bot.get_file(file_id)

            with tempfile.NamedTemporaryFile(delete=False) as f:
                await file.download_to_drive(f.name)
                path = f.name

            roll, name = extract_pdf(path)

            os.remove(path)

            if not roll:
                await update.message.reply_text("❌ Could not read PDF")
                continue

            con = db()
            cur = con.cursor()

            cur.execute("""
            INSERT OR REPLACE INTO records VALUES(?,?,?)
            """, (roll, name, file_id))

            con.commit()
            con.close()

            await update.message.reply_text(f"✅ Saved: {name}")

        except Exception as e:

            logging.error(e)
            await update.message.reply_text("⚠️ Processing failed")

        queue.task_done()


# =============== COMMANDS =================

async def start(update, context):

    txt = """
🤖 MLSU Admit Card Bot

📤 Forward PDFs (Max 50)

🔍 Search
/find <roll/name>

📊 Info
/stats

🚫 Admin
/block /unblock

⚡ Stable System
"""

    await update.message.reply_text(txt)


async def find(update, context):

    if not context.args:
        return await update.message.reply_text("Use: /find <roll/name>")

    q = " ".join(context.args).lower()

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT name, roll, file_id FROM records
    WHERE roll LIKE ? OR lower(name) LIKE ?
    """, (f"%{q}%", f"%{q}%"))

    rows = cur.fetchall()
    con.close()

    if not rows:
        return await update.message.reply_text("❌ Not found")

    for n, r, f in rows:

        if is_blocked(r):
            await update.message.reply_text(f"🚫 {r} blocked")
            continue

        await context.bot.send_document(
            update.effective_chat.id,
            f,
            caption=f"👤 {n}\n🎫 {r}"
        )


async def stats(update, context):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM records")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM blocked")
    blk = cur.fetchone()[0]

    con.close()

    await update.message.reply_text(
        f"📊 Records: {total}\n🚫 Blocked: {blk}\n📥 Queue: {queue.qsize()}"
    )


async def block(update, context):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        return

    roll = context.args[0]

    con = db()
    cur = con.cursor()

    cur.execute("INSERT OR IGNORE INTO blocked VALUES(?)", (roll,))

    con.commit()
    con.close()

    await update.message.reply_text(f"🚫 Blocked {roll}")


async def unblock(update, context):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        return

    roll = context.args[0]

    con = db()
    cur = con.cursor()

    cur.execute("DELETE FROM blocked WHERE roll=?", (roll,))

    con.commit()
    con.close()

    await update.message.reply_text(f"✅ Unblocked {roll}")


# =============== UPLOAD ==================

async def upload(update, context):

    if not is_admin(update.effective_user.id):
        return

    if queue.qsize() >= MAX_QUEUE:
        return await update.message.reply_text("⚠️ Queue full. Wait.")

    await queue.put(
        (update, context, update.message.document.file_id)
    )

    await update.message.reply_text("📥 Added to queue")


# =============== MAIN ===================

def main():

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))

    app.add_handler(
        MessageHandler(filters.Document.PDF, upload)
    )

    # Start background worker safely
    app.job_queue.run_once(
        lambda ctx: asyncio.create_task(worker()),
        when=1
    )

    print("🤖 Bot Running")

    app.run_polling()


if __name__ == "__main__":
    main()
