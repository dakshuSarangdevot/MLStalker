import os
import re
import sqlite3
import logging
import asyncio
import tempfile
import time

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
CHANNEL_ID = -1003702608871

DB_FILE = "data.db"
BATCH_SIZE = 50

# =========================================

logging.basicConfig(level=logging.INFO)

# ============ DATABASE ===================

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS progress(
        last_id INTEGER
    )
    """)

    cur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (OWNER_ID,))
    cur.execute("INSERT OR IGNORE INTO progress VALUES(0)")

    con.commit()
    con.close()


def db():
    return sqlite3.connect(DB_FILE)


# ============ HELPERS ===================

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


# ============ UI ===================

async def start(update, context):

    txt = """
🤖 MLSU Admit Card Bot

🔍 Search
/find <roll or name>

📊 Info
/stats

🔄 Recovery
/reindex
/status

🚫 Admin
/block /unblock
/admins

📤 Upload PDFs (Admin)

⚡ Stable • Secure • 24/7
"""

    await update.message.reply_text(txt)


# ============ SEARCH ===================

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
            await update.message.reply_text(f"🚫 {r} is blocked")
            continue

        await context.bot.send_document(
            update.effective_chat.id,
            f,
            caption=f"👤 {n}\n🎫 {r}"
        )


# ============ STATS ===================

async def stats(update, context):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM records")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM blocked")
    blk = cur.fetchone()[0]

    cur.execute("SELECT last_id FROM progress")
    prog = cur.fetchone()[0]

    con.close()

    await update.message.reply_text(
        f"📊 Records: {total}\n🚫 Blocked: {blk}\n📌 Progress: {prog}"
    )


# ============ ADMIN ===================

async def admins(update, context):

    if not is_admin(update.effective_user.id):
        return

    con = db()
    cur = con.cursor()
    cur.execute("SELECT uid FROM admins")

    rows = cur.fetchall()
    con.close()

    txt = "👑 Admins:\n\n"
    for r in rows:
        txt += str(r[0]) + "\n"

    await update.message.reply_text(txt)


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


# ============ UPLOAD ===================

async def upload(update, context):

    if not is_admin(update.effective_user.id):
        return

    doc = update.message.document
    file = await doc.get_file()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        await file.download_to_drive(f.name)
        path = f.name

    roll, name = extract_pdf(path)
    os.remove(path)

    if not roll:
        return await update.message.reply_text("❌ Read failed")

    con = db()
    cur = con.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO records VALUES(?,?,?)
    """, (roll, name, doc.file_id))

    con.commit()
    con.close()

    await update.message.reply_text(f"✅ Saved {name}")


# ============ REINDEX ===================

async def reindex(update, context):

    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("🔄 Reindex started...")

    con = db()
    cur = con.cursor()
    cur.execute("SELECT last_id FROM progress")
    last = cur.fetchone()[0]
    con.close()

    count = 0
    processed = 0

    async for m in context.bot.get_chat_history(CHANNEL_ID, limit=3000):

        if m.id <= last:
            continue

        if not m.document:
            continue

        if not m.document.file_name.lower().endswith(".pdf"):
            continue

        try:
            file = await m.document.get_file()

            with tempfile.NamedTemporaryFile(delete=False) as f:
                await file.download_to_drive(f.name)
                path = f.name

            roll, name = extract_pdf(path)
            os.remove(path)

            if roll:

                con = db()
                cur = con.cursor()

                cur.execute("""
                INSERT OR REPLACE INTO records VALUES(?,?,?)
                """, (roll, name, m.document.file_id))

                cur.execute("UPDATE progress SET last_id=?", (m.id,))

                con.commit()
                con.close()

                count += 1

        except:
            pass

        processed += 1

        if processed >= BATCH_SIZE:
            break

    await msg.edit_text(
        f"✅ Batch done\nProcessed: {processed}\nSaved: {count}"
    )


async def status(update, context):

    con = db()
    cur = con.cursor()
    cur.execute("SELECT last_id FROM progress")
    p = cur.fetchone()[0]
    con.close()

    await update.message.reply_text(f"📌 Last message: {p}")


# ============ MAIN ===================

def main():

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("reindex", reindex))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))

    app.add_handler(
        MessageHandler(filters.Document.PDF, upload)
    )

    print("🤖 Bot Running")

    app.run_polling()


if __name__ == "__main__":
    main()
