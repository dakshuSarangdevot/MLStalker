import os
import re
import sqlite3
import logging
import tempfile
import asyncio
import io

import pdfplumber

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


# ================= CONFIG =================

BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"
OWNER_ID = 8343668073

DB_FILE = "data.db"
MAX_QUEUE = 50
AUTO_BACKUP_AFTER = 50

# Google Drive
GDRIVE_KEY = "/etc/secrets/gdrive.json"
GDRIVE_FOLDER = "BotBackups"

# =========================================

logging.basicConfig(level=logging.INFO)


# =============== GLOBAL ==================

queue = asyncio.Queue()
processed = 0


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


# =============== GOOGLE DRIVE ================

def get_drive():

    creds = service_account.Credentials.from_service_account_file(
        GDRIVE_KEY,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )

    return build("drive", "v3", credentials=creds)


def get_folder_id(service):

    res = service.files().list(
        q=f"name='{GDRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder'",
        spaces="drive"
    ).execute()

    items = res.get("files", [])

    if not items:
        return None

    return items[0]["id"]


def upload_db():

    try:

        service = get_drive()
        folder = get_folder_id(service)

        if not folder:
            return False

        media = MediaFileUpload(DB_FILE)

        meta = {
            "name": "data_backup.db",
            "parents": [folder]
        }

        service.files().create(
            body=meta,
            media_body=media
        ).execute()

        return True

    except:
        return False


def download_db():

    try:

        service = get_drive()
        folder = get_folder_id(service)

        if not folder:
            return False

        res = service.files().list(
            q=f"name='data_backup.db' and '{folder}' in parents",
            spaces="drive"
        ).execute()

        items = res.get("files", [])

        if not items:
            return False

        file_id = items[0]["id"]

        req = service.files().get_media(fileId=file_id)

        fh = io.FileIO(DB_FILE, "wb")

        downloader = MediaIoBaseDownload(fh, req)

        done = False

        while not done:
            _, done = downloader.next_chunk()

        return True

    except:
        return False


def startup_restore():

    if not os.path.exists(DB_FILE):

        print("📦 Trying restore...")

        if download_db():
            print("✅ Restored")
        else:
            print("⚠️ No backup found")


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


# =============== WORKER ===================

async def worker(app):

    global processed

    print("⚙️ Worker started")

    while True:

        update, context, fid = await queue.get()

        try:

            file = await app.bot.get_file(fid)

            with tempfile.NamedTemporaryFile(delete=False) as f:
                await file.download_to_drive(f.name)
                path = f.name

            roll, name = extract_pdf(path)

            os.remove(path)

            if not roll:
                await update.message.reply_text("❌ Read failed")
                continue

            con = db()
            cur = con.cursor()

            cur.execute("""
            INSERT OR REPLACE INTO records VALUES(?,?,?)
            """, (roll, name, fid))

            con.commit()
            con.close()

            processed += 1

            await update.message.reply_text(f"✅ {name}")

            if processed % AUTO_BACKUP_AFTER == 0:

                if upload_db():
                    await update.message.reply_text("☁️ Auto backup done")

        except Exception as e:

            logging.error(e)
            await update.message.reply_text("⚠️ Failed")

        queue.task_done()


# =============== COMMANDS =================

async def start(update, context):

    txt = """
🤖 MLSU Admit Card Bot

━━━━━━━━━━━━━━━

📤 Upload PDFs (Max 50)
🔍 /find <roll/name>
📊 /stats

👑 Admin
/addadmin <id>
/removeadmin <id>
/admins

🚫 Block
/block <roll>
/unblock <roll>

☁️ Auto Backup

━━━━━━━━━━━━━━━
"""

    await update.message.reply_text(txt)


async def stats(update, context):

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM records")
    total = cur.fetchone()[0]

    con.close()

    await update.message.reply_text(
        f"""
📊 Status

Records: {total}
Queue: {queue.qsize()}
Processed: {processed}
"""
    )


async def find(update, context):

    if not context.args:
        return await update.message.reply_text("Use /find <roll/name>")

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
            continue

        await context.bot.send_document(
            update.effective_chat.id,
            f,
            caption=f"{n} | {r}"
        )


# =============== ADMIN ===================

async def addadmin(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    uid = int(context.args[0])

    con = db()
    cur = con.cursor()

    cur.execute("INSERT OR IGNORE INTO admins VALUES(?)", (uid,))
    con.commit()
    con.close()

    await update.message.reply_text("✅ Admin added")


async def removeadmin(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    uid = int(context.args[0])

    con = db()
    cur = con.cursor()

    cur.execute("DELETE FROM admins WHERE uid=?", (uid,))
    con.commit()
    con.close()

    await update.message.reply_text("❌ Admin removed")


async def admins(update, context):

    if not is_admin(update.effective_user.id):
        return

    con = db()
    cur = con.cursor()

    cur.execute("SELECT uid FROM admins")
    rows = cur.fetchall()

    con.close()

    txt = "Admins:\n\n"

    for r in rows:
        txt += f"{r[0]}\n"

    await update.message.reply_text(txt)


async def block(update, context):

    if not is_admin(update.effective_user.id):
        return

    roll = context.args[0]

    con = db()
    cur = con.cursor()

    cur.execute("INSERT OR IGNORE INTO blocked VALUES(?)", (roll,))
    con.commit()
    con.close()

    await update.message.reply_text("🚫 Blocked")


async def unblock(update, context):

    if not is_admin(update.effective_user.id):
        return

    roll = context.args[0]

    con = db()
    cur = con.cursor()

    cur.execute("DELETE FROM blocked WHERE roll=?", (roll,))
    con.commit()
    con.close()

    await update.message.reply_text("✅ Unblocked")


# =============== UPLOAD ==================

async def upload(update, context):

    if not is_admin(update.effective_user.id):
        return

    if queue.qsize() >= MAX_QUEUE:
        return await update.message.reply_text("⚠️ Queue full")

    await queue.put(
        (update, context, update.message.document.file_id)
    )

    await update.message.reply_text("📥 Queued")


# =============== MAIN ===================

async def main():

    startup_restore()
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("admins", admins))

    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))

    app.add_handler(
        MessageHandler(filters.Document.PDF, upload)
    )

    asyncio.create_task(worker(app))

    print("🤖 Bot Running")

    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
