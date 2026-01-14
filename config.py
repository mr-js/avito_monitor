# ==================== CONFIGURATION ====================
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.absolute()

# Logging configuration
LOG_ENABLED = True
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "avito_monitor.log"
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5
LOG_ENCODING = "utf-8"

# Ensure log directory exists
LOG_DIR.mkdir(exist_ok=True)

# Auto-reply configuration
AUTO_REPLY_ENABLED = True  # Set to False to disable auto-reply
AUTO_REPLY_MESSAGE = "Напишите мне в Telegram для быстрого ответа: @mr0js"
AUTO_REPLY_DELAY = 2.0  # Delay between replies in seconds

# Monitoring configuration
CHECK_INTERVAL = 30  # Seconds between checks (when no new messages)
MAX_CHATS = 200  # Maximum number of chats to retrieve
BATCH_SIZE = 50  # Chats per API request
MAX_RETRIES = 3  # Maximum retries for API calls
RETRY_DELAY = 5  # Seconds between retries

# File storage
JSON_FILENAME = BASE_DIR / "avito_chats.json"
STATE_FILENAME = BASE_DIR / "monitor_state.json"

# Service name for keyring
SERVICE_NAME = "avito-api"

# Web interface configuration
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000
WEB_DEBUG = False
AUTO_START_MONITOR = True  # Автозапуск мониторинга при старте Flask

# Display configuration
SHOW_RECENT_CHATS = 10  # Number of recent chats to display

# System messages that should be notified but not auto-replied
SYSTEM_MESSAGES = [
    "перейдите на подписку с api мессенджера",
    "подписка с api мессенджера", 
    "чтобы получить доступ к чатам",
    "api мессенджера",
    "подписка api мессенджера"
]

# API endpoints
AVITO_TOKEN_URL = "https://api.avito.ru/token"
AVITO_CHATS_URL_TEMPLATE = "https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"
AVITO_SEND_MESSAGE_URL_TEMPLATE = "https://api.avito.ru/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
# ======================================================