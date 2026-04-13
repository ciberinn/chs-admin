import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- НАСТРОЙКИ (ВАШИ ДАННЫЕ) ---
BOT_TOKEN = "8374295168:AAEtuw4uSqlb4yq-eI-337xFFzIauhUi4-A"
SPREADSHEET_ID = "19oqV1k2sv6nXvLLDMaQeYV_hOvHsG5nF2NllZji1b0M"
ADMIN_TELEGRAM_ID = 8303713438  # ID главного администратора
CREDENTIALS_FILE = "credentials.json"  # Файл с ключами сервисного аккаунта Google

# Состояния для диалога добавления записи
ADDING_FULLNAME, ADDING_ACCOUNTID, ADDING_REASON, ADDING_ADDITIONALINFO = range(4)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Подключение к Google Sheets ---
def get_google_sheet(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet.worksheet(sheet_name)

# --- Проверка доступа ---
def is_user_authorized(telegram_id):
    try:
        users_sheet = get_google_sheet("Users")
        users_data = users_sheet.get_all_values()[1:]
        for row in users_data:
            if row and row[0] == str(telegram_id):
                return True
    except Exception as e:
        logger.error(f"Ошибка проверки доступа: {e}")
    return False

def is_admin(telegram_id):
    try:
        users_sheet = get_google_sheet("Users")
        users_data = users_sheet.get_all_values()[1:]
        for row in users_data:
            if row and row[0] == str(telegram_id) and len(row) > 2 and row[2].lower() == "admin":
                return True
    except Exception as e:
        logger.error(f"Ошибка проверки прав админа: {e}")
    return False

# --- Работа с ЧС ---
def add_to_blacklist(full_name, account_id, reason, added_by, additional_info=""):
    try:
        blacklist_sheet = get_google_sheet("Blacklist")
        import time
        from datetime import datetime
        new_id = str(int(time.time()))
        date_added = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        blacklist_sheet.append_row([new_id, full_name, account_id, reason, date_added, added_by, additional_info])
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления в ЧС: {e}")
        return False

def search_in_blacklist(query):
    try:
        blacklist_sheet = get_google_sheet("Blacklist")
        data = blacklist_sheet.get_all_values()
        headers = data[0]
        results = []
        for row in data[1:]:
            if any(query.lower() in str(cell).lower() for cell in row):
                result_dict = dict(zip(headers, row))
                results.append(result_dict)
        return results
    except Exception as e:
        logger.error(f"Ошибка поиска в ЧС: {e}")
        return []

# --- Команды бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_user_authorized(user_id):
        await update.message.reply_text(
            "🛡️ *ЧС Бот Администрации*\n\n"
            "Вы авторизованы.\n\n"
            "📌 Команды:\n"
            "/add — Добавить запись в ЧС\n"
            "/search [запрос] — Поиск по базе\n"
            "/help — Помощь",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⛔ Доступ запрещён.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# --- Диалог добавления записи ---
async def add_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return ConversationHandler.END
    await update.message.reply_text("Введите *ФИО* нарушителя:", parse_mode="Markdown")
    return ADDING_FULLNAME

async def add_entry_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Введите *ID аккаунта*:", parse_mode="Markdown")
    return ADDING_ACCOUNTID

async def add_entry_accountid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['account_id'] = update.message.text
    await update.message.reply_text("Введите *причину*:", parse_mode="Markdown")
    return ADDING_REASON

async def add_entry_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['reason'] = update.message.text
    await update.message.reply_text("Введите *доп. информацию* (или `нет`):", parse_mode="Markdown")
    return ADDING_ADDITIONALINFO

async def add_entry_additional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    additional_info = update.message.text if update.message.text.lower() != "нет" else ""
    success = add_to_blacklist(
        full_name=context.user_data['full_name'],
        account_id=context.user_data['account_id'],
        reason=context.user_data['reason'],
        added_by=str(user_id),
        additional_info=additional_info
    )
    if success:
        await update.message.reply_text("✅ Запись добавлена в ЧС.")
    else:
        await update.message.reply_text("❌ Ошибка при добавлении.")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Добавление отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# --- Поиск ---
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Укажите запрос: `/search Иванов`")
        return
    results = search_in_blacklist(query)
    if results:
        for item in results:
            response = (
                f"*ID:* {item.get('ID', '—')}\n"
                f"*ФИО:* {item.get('FullName', '—')}\n"
                f"*Аккаунт:* {item.get('AccountID', '—')}\n"
                f"*Причина:* {item.get('Reason', '—')}\n"
                f"*Дата:* {item.get('DateAdded', '—')}\n"
                f"*Кем добавлен:* {item.get('AddedBy', '—')}\n"
                f"*Доп.:* {item.get('AdditionalInfo', '—')}"
            )
            await update.message.reply_text(response, parse_mode="Markdown")
    else:
        await update.message.reply_text("🔎 Ничего не найдено.")

# --- Запуск ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add_entry_start)],
        states={
            ADDING_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_fullname)],
            ADDING_ACCOUNTID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_accountid)],
            ADDING_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_reason)],
            ADDING_ADDITIONALINFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_additional)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))

    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
