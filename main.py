import os
import re
import sqlite3
import logging

import pdfplumber

from telegram import Update, Document
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

# =========================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ============ DATABASE ===================

def init_db():

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY,
        roll TEXT,
        name TEXT,
        file_id TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins(
        user_id INTEGER UNIQUE
    )
    """)

    cur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (OWNER_ID,))

    con.commit()
    con.close()


def db():
    return sqlite3.connect(DB_FILE)


# ============ HELPERS ===================

def is_admin(uid):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    r = cur.fetchone()

    con.close()
    return r is not None


async def notify_owner(context, text):

    try:
        await context.bot.send_message(OWNER_ID, text)
    except:
        pass


def extract_info(pdf_path):

    with pdfplumber.open(pdf_path) as pdf:

        page = pdf.pages[0]
        text = page.extract_text()

    roll = re.search(r"Roll No\.\s*:\s*(\d+)", text)
    name = re.search(r"Candidate's Name\s*:\s*(.+)", text)

    if not roll or not name:
        return None, None

    return roll.group(1).strip(), name.group(1).strip()


# ============ COMMANDS ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = """
🤖 MLSU Admit Card Bot

🔍 Search:
/find <roll/name>

📊 Info:
/stats

📤 Upload PDF (Admin only)

👑 Admin:
/makeadmin <id>
/adminlist
/clear

⚡ Fast • Secure • Tracked
"""

    await update.message.reply_text(msg)


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    uid = user.id
    uname = user.full_name

    if not context.args:
        await update.message.reply_text("Usage: /find <roll/name>")
        return

    q = " ".join(context.args)

    # Notify Owner
    await notify_owner(
        context,
        f"🔍 Search Used\nUser: {uname} ({uid})\nQuery: {q}"
    )

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT name, roll, file_id FROM records
    WHERE roll LIKE ? OR LOWER(name) LIKE ?
    """, (f"%{q}%", f"%{q.lower()}%"))

    rows = cur.fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("❌ Not found")
        return

    for n, r, fid in rows:

        cap = f"👤 {n}\n🎫 Roll: {r}"

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=fid,
            caption=cap
        )


async def stats(update: Update, context):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM records")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM admins")
    adm = cur.fetchone()[0]

    con.close()

    await update.message.reply_text(
        f"📊 Records: {total}\n👑 Admins: {adm}"
    )


# ============ ADMIN ===================

async def makeadmin(update: Update, context):

    if update.effective_user.id != OWNER_ID:
        return

    if not context.args:
        await update.message.reply_text("/makeadmin <id>")
        return

    uid = int(context.args[0])

    con = db()
    cur = con.cursor()

    cur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (uid,))
    con.commit()
    con.close()

    await update.message.reply_text("✅ Admin added")

    await notify_owner(context, f"👑 New Admin: {uid}")


async def adminlist(update, context):

    if not is_admin(update.effective_user.id):
        return

    con = db()
    cur = con.cursor()

    cur.execute("SELECT user_id FROM admins")
    rows = cur.fetchall()
    con.close()

    txt = "👑 Admins:\n\n"

    for r in rows:
        txt += f"{r[0]}\n"

    await update.message.reply_text(txt)


async def clear(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    con = db()
    cur = con.cursor()

    cur.execute("DELETE FROM records")
    con.commit()
    con.close()

    await update.message.reply_text("🗑 Database cleared")

    await notify_owner(context, "⚠️ Database cleared")


# ============ UPLOADER ===================

async def handle_pdf(update: Update, context):

    if not is_admin(update.effective_user.id):
        return

    doc: Document = update.message.document

    if not doc.file_name.lower().endswith(".pdf"):
        return

    file = await doc.get_file()

    path = f"temp_{doc.file_unique_id}.pdf"

    await file.download_to_drive(path)

    roll, name = extract_info(path)

    os.remove(path)

    if not roll:
        await update.message.reply_text("❌ Could not read PDF")
        return

    con = db()
    cur = con.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO records(roll,name,file_id)
    VALUES(?,?,?)
    """, (roll, name, doc.file_id))

    con.commit()
    con.close()

    await update.message.reply_text(
        f"✅ Saved: {name} ({roll})"
    )


# ============ MAIN ===================

def main():

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("makeadmin", makeadmin))
    app.add_handler(CommandHandler("adminlist", adminlist))
    app.add_handler(CommandHandler("clear", clear))

    app.add_handler(
        MessageHandler(filters.Document.PDF, handle_pdf)
    )

    print("🤖 Bot Started Successfully")

    app.run_polling()


if __name__ == "__main__":
    main()
