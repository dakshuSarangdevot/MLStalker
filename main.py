import os
import io
import time
import logging
import sqlite3

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


# ================= CONFIG =================

# 🔴 PASTE YOUR BOT TOKEN INSIDE QUOTES
BOT_TOKEN = "7739387244:AAEMOHPjsZeJ95FbLjk-xoqy1LO5doYez98"
# Your Telegram ID (already set)
OWNER_ID = 8343668073

# Database file
DB_FILE = "data.db"

# Google Drive
GDRIVE_KEY = "/etc/secrets/gdrive.json"
GDRIVE_FOLDER = "BotBackups"

# =========================================

logging.basicConfig(level=logging.WARNING)


# =============== DATABASE =================

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

    con.commit()
    con.close()


# =============== GOOGLE DRIVE =================

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
        raise Exception("Backup folder not found")

    return items[0]["id"]


def upload_db():

    service = get_drive()
    folder = get_folder_id(service)

    media = MediaFileUpload(DB_FILE)

    meta = {
        "name": "data_backup.db",
        "parents": [folder]
    }

    service.files().create(
        body=meta,
        media_body=media
    ).execute()


def download_db():

    service = get_drive()
    folder = get_folder_id(service)

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


# =============== AUTO RESTORE =================

def startup_restore():

    if not os.path.exists(DB_FILE):

        print("DB missing. Restoring from Drive...")

        try:
            ok = download_db()

            if ok:
                print("Restore complete")
            else:
                print("No backup found")

        except Exception as e:
            print("Restore failed:", e)


# =============== COMMANDS =================

async def start(update, context):

    await update.message.reply_text("🤖 Bot is running!")


async def backup(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    await update.message.reply_text("📦 Backing up...")

    try:
        upload_db()
        await update.message.reply_text("✅ Backup saved")

    except Exception as e:
        await update.message.reply_text("❌ Backup failed")
        print(e)


async def restore(update, context):

    if update.effective_user.id != OWNER_ID:
        return

    await update.message.reply_text("♻️ Restoring...")

    try:
        download_db()
        await update.message.reply_text("✅ Restored. Restart bot.")

    except Exception as e:
        await update.message.reply_text("❌ Restore failed")
        print(e)


# =============== MAIN =================

def main():

    # Auto restore DB
    startup_restore()

    # Init DB
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("restore", restore))

    print("🤖 Bot running...")

    app.run_polling()


# Auto restart on crash
while True:

    try:
        main()

    except Exception as e:

        print("Crashed:", e)
        time.sleep(10)
