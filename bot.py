import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8374295168:AAEtuw4uSqlb4yq-eI-337xFFzIauhUi4-A"
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzmJ5oZIpEAEotApnI30Kd2VB6kxXKk-ktMiXlfLSk-EpLupg47WkHWnrlPsN80qRmvcw/exec"

# Состояния диалога
ADDING_FULLNAME, ADDING_ACCOUNTID, ADDING_REASON, ADDING_ADDITIONALINFO = range(4)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- HTTP-запросы к Apps Script ---
def call_script(action, data):
    try:
        response = requests.post(SCRIPT_URL + "?action=" + action, json=data, timeout=15)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка запроса к скрипту: {e}")
        return {"success": False, "message": "Ошибка соединения с сервером"}

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ *ЧС Бот Администрации*\n\n"
        "/add — Добавить запись\n"
        "/search [запрос] — Поиск\n"
        "/help — Помощь",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# --- Диалог добавления ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите *ФИО* нарушителя:", parse_mode="Markdown")
    return ADDING_FULLNAME

async def add_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['fullName'] = update.message.text
    await update.message.reply_text("Введите *ID аккаунта*:", parse_mode="Markdown")
    return ADDING_ACCOUNTID

async def add_accountid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['accountId'] = update.message.text
    await update.message.reply_text("Введите *причину*:", parse_mode="Markdown")
    return ADDING_REASON

async def add_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reason'] = update.message.text
    await update.message.reply_text("Введите *доп. информацию* (или `нет`):", parse_mode="Markdown")
    return ADDING_ADDITIONALINFO

async def add_additional(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    additional = update.message.text if update.message.text.lower() != "нет" else ""
    
    data = {
        "telegramId": user_id,
        "fullName": context.user_data['fullName'],
        "accountId": context.user_data['accountId'],
        "reason": context.user_data['reason'],
        "additionalInfo": additional
    }
    result = call_script("add", data)
    if result.get("success"):
        await update.message.reply_text(f"✅ Запись добавлена. ID: {result.get('id')}")
    else:
        await update.message.reply_text(f"❌ {result.get('message', 'Ошибка')}")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# --- Поиск ---
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Укажите запрос: `/search Иванов`")
        return
    
    data = {"telegramId": user_id, "query": query}
    results = call_script("search", data)
    if isinstance(results, list):
        if results:
            for item in results:
                text = (f"*ID:* {item.get('ID','—')}\n"
                        f"*ФИО:* {item.get('FullName','—')}\n"
                        f"*Аккаунт:* {item.get('AccountID','—')}\n"
                        f"*Причина:* {item.get('Reason','—')}\n"
                        f"*Дата:* {item.get('DateAdded','—')}\n"
                        f"*Доп.:* {item.get('AdditionalInfo','—')}")
                await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text("🔎 Ничего не найдено.")
    else:
        await update.message.reply_text(f"❌ {results.get('message', 'Ошибка')}")

# --- Запуск ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('add', add_start)],
        states={
            ADDING_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_fullname)],
            ADDING_ACCOUNTID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_accountid)],
            ADDING_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reason)],
            ADDING_ADDITIONALINFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_additional)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search_command))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()