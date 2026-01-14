"""
Avito Chat Monitor API Module
Can be imported and used in other applications
"""
import requests
import keyring
import getpass
import json
import datetime
import time
import logging
import logging.handlers
from typing import Optional, List, Dict, Any, Set, Tuple
from collections import defaultdict
from pathlib import Path

# Import configuration
try:
    from config import (
        AUTO_REPLY_ENABLED, AUTO_REPLY_MESSAGE, AUTO_REPLY_DELAY,
        CHECK_INTERVAL, MAX_CHATS, BATCH_SIZE, MAX_RETRIES, RETRY_DELAY,
        JSON_FILENAME, STATE_FILENAME, SERVICE_NAME,
        AVITO_TOKEN_URL, AVITO_CHATS_URL_TEMPLATE, AVITO_SEND_MESSAGE_URL_TEMPLATE,
        LOG_DIR, LOG_FILE, LOG_LEVEL, LOG_FORMAT, LOG_MAX_SIZE, LOG_BACKUP_COUNT, LOG_ENCODING,
        SYSTEM_MESSAGES
    )
except ImportError:
    # Default values if config not found
    AUTO_REPLY_ENABLED = True
    AUTO_REPLY_MESSAGE = "Напишите мне в Telegram для быстрого ответа: @mr0js"
    AUTO_REPLY_DELAY = 2.0
    CHECK_INTERVAL = 30
    MAX_CHATS = 200
    BATCH_SIZE = 50
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    JSON_FILENAME = "avito_chats.json"
    STATE_FILENAME = "monitor_state.json"
    SERVICE_NAME = "avito-api"
    AVITO_TOKEN_URL = "https://api.avito.ru/token"
    AVITO_CHATS_URL_TEMPLATE = "https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"
    AVITO_SEND_MESSAGE_URL_TEMPLATE = "https://api.avito.ru/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
    LOG_DIR = "logs"
    LOG_FILE = "logs/avito_monitor.log"
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_MAX_SIZE = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 5
    LOG_ENCODING = "utf-8"
    SYSTEM_MESSAGES = [
        "перейдите на подписку с api мессенджера",
        "подписка с api мессенджера",
        "чтобы получить доступ к чатам",
        "api мессенджера",
        "подписка api мессенджера"
    ]

class AvitoLogger:
    """Logging wrapper for Avito API"""
    
    _logger_initialized = False
    
    @staticmethod
    def setup_logging():
        """Setup file logging with UTF-8 encoding"""
        if AvitoLogger._logger_initialized:
            return logging.getLogger("avito_monitor")
        
        # Create logger
        logger = logging.getLogger("avito_monitor")
        logger.setLevel(getattr(logging, LOG_LEVEL))
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # Create rotating file handler with UTF-8 encoding
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding=LOG_ENCODING
        )
        file_handler.setLevel(getattr(logging, LOG_LEVEL))
        
        # Create formatter
        formatter = logging.Formatter(LOG_FORMAT)
        file_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(file_handler)
        
        # Also log to console for debugging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        AvitoLogger._logger_initialized = True
        return logger
    
    @staticmethod
    def log(level: str, message: str, **kwargs):
        """Log message with given level"""
        logger = logging.getLogger("avito_monitor")
        log_method = getattr(logger, level.lower(), logger.info)
        
        # Format message with kwargs if present
        if kwargs:
            details = " | ".join(f"{k}: {v}" for k, v in kwargs.items())
            message = f"{message} - {details}"
        
        log_method(message)
        
        # Also store error for web interface
        if level.lower() in ["error", "warning"]:
            AvitoLogger.store_message(level, message)

    @staticmethod
    def store_message(level: str, message: str):
        """Store message for web interface access"""
        try:
            message_log = {
                'timestamp': datetime.datetime.now().isoformat(),
                'message': message,
                'type': level.lower(),
                'level': level.upper()
            }
            
            # Store in a simple messages file
            messages_file = LOG_DIR / "messages.json"
            messages = []
            
            if messages_file.exists():
                try:
                    with open(messages_file, 'r', encoding='utf-8') as f:
                        messages = json.load(f)
                        if not isinstance(messages, list):
                            messages = []
                except:
                    messages = []
            
            # Keep only last 100 messages
            messages.append(message_log)
            if len(messages) > 100:
                messages = messages[-100:]
            
            with open(messages_file, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Error storing message log: {e}")

def get_credentials():
    """
    Retrieves or prompts for credentials using keyring.
    """
    # Try to get saved data
    client_id = keyring.get_password(SERVICE_NAME, "client_id")
    client_secret = keyring.get_password(SERVICE_NAME, "client_secret")
    user_id = keyring.get_password(SERVICE_NAME, "user_id")
    
    # If some data is missing, prompt the user
    if not client_id:
        client_id = input("Enter Client ID: ").strip()
        keyring.set_password(SERVICE_NAME, "client_id", client_id)
        AvitoLogger.log("info", "Client ID saved to keyring")
    
    if not client_secret:
        client_secret = getpass.getpass("Enter Client Secret: ").strip()
        keyring.set_password(SERVICE_NAME, "client_secret", client_secret)
        AvitoLogger.log("info", "Client Secret saved to keyring")
    
    if not user_id:
        user_id = input("Enter User ID: ").strip()
        keyring.set_password(SERVICE_NAME, "user_id", user_id)
        AvitoLogger.log("info", "User ID saved to keyring")
    
    return client_id, client_secret, user_id

def clear_credentials():
    """
    Deletes saved credentials from keyring.
    """
    keyring.delete_password(SERVICE_NAME, "client_id")
    keyring.delete_password(SERVICE_NAME, "client_secret")
    keyring.delete_password(SERVICE_NAME, "user_id")
    AvitoLogger.log("warning", "Credentials deleted from keyring")

def is_system_message(text: str) -> bool:
    """
    Check if message is a system message that should not be auto-replied.
    
    :param text: Message text
    :return: True if message is a system message
    """
    if not text:
        return False
    
    text_lower = text.lower()
    for phrase in SYSTEM_MESSAGES:
        if phrase in text_lower:
            AvitoLogger.log("debug", f"Detected system message containing phrase: {phrase}")
            return True
    
    return False

def extract_user_name(chat_data: Dict) -> str:
    """
    Extract user name from chat data.
    
    :param chat_data: Chat data dictionary
    :return: User name or 'Unknown User'
    """
    try:
        # Check for users in chat
        users = chat_data.get('users', [])
        if users and isinstance(users, list):
            for user in users:
                if isinstance(user, dict):
                    name = user.get('name', {})
                    
                    if name and name.strip():
                        return name.strip()
        
        # Try to get name from chat metadata
        chat_name = chat_data.get('name') or chat_data.get('title')
        if chat_name and chat_name.strip():
            return chat_name.strip()
        
        # Try to get name from context
        context = chat_data.get('context', {})
        if context:
            item_title = context.get('item_title')
            if item_title and item_title.strip():
                return f"User from: {item_title.strip()}"
        
    except Exception as e:
        AvitoLogger.log("debug", f"Error extracting user name: {e}")
    
    # Last resort: try to extract from chat ID
    chat_id = str(chat_data.get('id', ''))
    if chat_id and len(chat_id) > 10:
        return f"User_{chat_id[-8:]}"
    
    return "Unknown User"

class AutoReplyManager:
    """Manages automatic replies to new messages"""
    
    def __init__(self, client_id: str, client_secret: str, user_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.access_token = None
        self.token_expires = None
        self.sent_replies = set()  # Track chat IDs we've already replied to
        
        # Load previously sent replies from file
        self._load_sent_replies()
        
    def _load_sent_replies(self):
        """Load sent replies from state file"""
        try:
            if STATE_FILENAME.exists():
                with open(STATE_FILENAME, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.sent_replies = set(state.get('sent_replies', []))
                    AvitoLogger.log("info", f"Loaded {len(self.sent_replies)} sent replies from state file")
        except Exception as e:
            AvitoLogger.log("error", f"Error loading state file: {e}")
            self.sent_replies = set()
    
    def _save_sent_replies(self):
        """Save sent replies to state file"""
        try:
            # Load existing state
            state = {}
            if STATE_FILENAME.exists():
                with open(STATE_FILENAME, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            
            # Update processed IDs and sent replies
            state['sent_replies'] = list(self.sent_replies)
            state['last_updated'] = datetime.datetime.now().isoformat()
            
            with open(STATE_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            AvitoLogger.log("error", f"Error saving state file: {e}")
    
    def get_access_token(self, force_refresh=False):
        """
        Obtains access_token for sending messages.
        """
        if not force_refresh and self.access_token and self.token_expires:
            if datetime.datetime.now() < self.token_expires:
                return self.access_token
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = requests.post(AVITO_TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 86400)
            self.token_expires = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 300)
            
            AvitoLogger.log("debug", "Access token obtained for sending messages")
            return self.access_token
            
        except requests.exceptions.HTTPError as e:
            AvitoLogger.log("error", f"Error getting token for auto-reply: {e}")
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                    AvitoLogger.log("error", f"Token error details: {error_detail}")
                except:
                    AvitoLogger.log("error", f"Token error response: {e.response.text}")
            raise
    
    def send_auto_reply(self, chat_id: str, user_name: str, message_text: str = None) -> Dict:
        """
        Sends an automatic reply to a chat.
        
        :param chat_id: Chat ID to send message to
        :param user_name: Name of the user
        :param message_text: Custom message text
        :return: Response from API
        """
        if message_text is None:
            message_text = AUTO_REPLY_MESSAGE
        
        # Check if we've already replied to this chat
        if chat_id in self.sent_replies:
            AvitoLogger.log("info", f"Already replied to chat {chat_id} (user: {user_name}), skipping")
            return {"status": "already_replied"}
        
        # Get access token
        try:
            token = self.get_access_token()
        except Exception as e:
            AvitoLogger.log("error", f"Failed to get token for chat {chat_id} (user: {user_name}): {e}")
            return {"error": f"Token error: {str(e)}"}
        
        url = AVITO_SEND_MESSAGE_URL_TEMPLATE.format(
            user_id=self.user_id,
            chat_id=chat_id
        )
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "message": {
                "text": message_text
            },
            "type": "text"
        }
        
        try:
            AvitoLogger.log("info", f"Sending auto-reply to {user_name} (chat: {chat_id})")
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Mark this chat as replied to and save
            self.sent_replies.add(chat_id)
            self._save_sent_replies()
            
            AvitoLogger.log("info", f"Auto-reply sent successfully to {user_name}")
            
            return result
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error sending to {user_name}"
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg}: Status {e.response.status_code} - {error_detail}"
                except:
                    error_msg = f"{error_msg}: Status {e.response.status_code} - {e.response.text}"
            
            AvitoLogger.log("error", error_msg)
            return {"error": error_msg}
        
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error sending to {user_name}: {e}"
            AvitoLogger.log("error", error_msg)
            return {"error": error_msg}
        
        except Exception as e:
            error_msg = f"Unexpected error sending auto-reply to {user_name}: {e}"
            AvitoLogger.log("error", error_msg)
            return {"error": error_msg}
    
    def process_auto_replies(self, unread_messages: List[Dict]):
        """
        Processes auto-replies for unread messages.
        
        :param unread_messages: List of unread messages with user names
        :return: List of successfully sent replies
        """
        if not unread_messages:
            return []
        
        # Filter out system messages (show notification but don't reply)
        regular_messages = [msg for msg in unread_messages if not msg.get('is_system', False)]
        
        if not regular_messages:
            AvitoLogger.log("info", "Only system messages found, no auto-replies to send")
            return []
        
        AvitoLogger.log("info", f"Processing auto-replies for {len(regular_messages)} regular message(s)")
        
        sent_replies = []
        failed_replies = []
        
        for i, message in enumerate(regular_messages, 1):
            chat_id = message['chat_id']
            user_name = message.get('user_name', 'Unknown User')
            message_text = message.get('text', '')
            message_id = message.get('message_id', '')
            
            AvitoLogger.log("info", f"[{i}/{len(regular_messages)}] Processing message from {user_name} (ID: {message_id[:8]}...): {message_text[:60]}...")
            
            result = self.send_auto_reply(chat_id, user_name)
            
            if "error" not in result and result.get("status") != "already_replied":
                sent_replies.append({
                    'chat_id': chat_id,
                    'user_name': user_name,
                    'message_id': result.get('id'),
                    'original_message_id': message_id,
                    'timestamp': datetime.datetime.now().isoformat()
                })
                AvitoLogger.log("info", f"Successfully sent auto-reply to {user_name}")
            elif "error" in result:
                failed_replies.append({
                    'chat_id': chat_id,
                    'user_name': user_name,
                    'error': result['error']
                })
                AvitoLogger.log("error", f"Failed to send auto-reply to {user_name}: {result['error']}")
            
            # Add delay between replies
            if i < len(regular_messages):
                time.sleep(AUTO_REPLY_DELAY)
        
        if sent_replies:
            AvitoLogger.log("info", f"Successfully sent {len(sent_replies)} auto-reply(s)")
        
        if failed_replies:
            AvitoLogger.log("warning", f"Failed to send {len(failed_replies)} auto-reply(s)")
        
        return sent_replies

class AvitoChatMonitor:
    """
    Main Avito Chat Monitor class.
    Can be used as a standalone service or imported into other applications.
    """
    
    def __init__(self, auto_reply_enabled=None):
        AvitoLogger.setup_logging()
        
        try:
            self.client_id, self.client_secret, self.user_id = get_credentials()
            self.access_token = None
            self.token_expires = None
            
            self.auto_reply_manager = AutoReplyManager(self.client_id, self.client_secret, self.user_id)
            
            # Use provided value or default from config
            self.auto_reply_enabled = auto_reply_enabled if auto_reply_enabled is not None else AUTO_REPLY_ENABLED
            self.processed_message_ids = set()  # Track processed message IDs by their ID
            
            # Initialize with empty state if no JSON file
            self._ensure_json_file()
            
            # Load previously processed message IDs from file
            self._load_processed_ids()
            
            # Statistics
            self.stats = {
                'start_time': datetime.datetime.now().isoformat(),
                'total_checks': 0,
                'total_unread_messages': 0,
                'total_auto_replies': 0,
                'total_system_messages': 0,
                'total_regular_messages': 0,
                'last_check': None,
                'last_unread_count': 0,
                'last_error': None,
                'auto_reply_enabled': self.auto_reply_enabled,
                'last_user_names': []  # Store last few user names
            }
            
            if self.auto_reply_enabled:
                AvitoLogger.log("info", f"Auto-reply enabled: {AUTO_REPLY_MESSAGE}")
            else:
                AvitoLogger.log("info", "Auto-reply disabled")
                
        except Exception as e:
            AvitoLogger.log("error", f"Error initializing AvitoChatMonitor: {e}")
            raise
    
    def _ensure_json_file(self):
        """Ensure JSON file exists with basic structure"""
        try:
            if not JSON_FILENAME.exists():
                empty_data = {
                    'chats': [],
                    'total_chats': 0,
                    'retrieved_at': datetime.datetime.now().isoformat(),
                    'retrieved_at_formatted': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
                    json.dump(empty_data, f, ensure_ascii=False, indent=2)
                AvitoLogger.log("info", f"Created empty JSON file: {JSON_FILENAME}")
        except Exception as e:
            AvitoLogger.log("error", f"Error creating JSON file: {e}")
    
    def _load_processed_ids(self):
        """Load processed message IDs from state file"""
        try:
            if STATE_FILENAME.exists():
                with open(STATE_FILENAME, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.processed_message_ids = set(state.get('processed_message_ids', []))
                    AvitoLogger.log("info", f"Loaded {len(self.processed_message_ids)} processed message IDs from state file")
        except Exception as e:
            AvitoLogger.log("error", f"Error loading processed IDs: {e}")
            self.processed_message_ids = set()
    
    def _save_processed_ids(self):
        """Save processed message IDs to state file"""
        try:
            # Load existing state
            state = {}
            if STATE_FILENAME.exists():
                with open(STATE_FILENAME, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            
            # Update processed IDs
            state['processed_message_ids'] = list(self.processed_message_ids)
            state['last_updated'] = datetime.datetime.now().isoformat()
            
            # Keep only last 1000 IDs to prevent file from growing too large
            if len(state['processed_message_ids']) > 1000:
                state['processed_message_ids'] = state['processed_message_ids'][-1000:]
                AvitoLogger.log("info", f"Trimmed processed IDs to last 1000 entries")
            
            with open(STATE_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            AvitoLogger.log("error", f"Error saving processed IDs: {e}")
    
    def reset_processed_ids(self):
        """Reset processed message IDs (for testing/debugging)"""
        self.processed_message_ids = set()
        self._save_processed_ids()
        AvitoLogger.log("info", "Reset all processed message IDs")
    
    def get_access_token(self, force_refresh=False):
        """
        Obtains access_token for reading chats.
        """
        if not force_refresh and self.access_token and self.token_expires:
            if datetime.datetime.now() < self.token_expires:
                return self.access_token
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = requests.post(AVITO_TOKEN_URL, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 86400)
            self.token_expires = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 300)
            
            AvitoLogger.log("debug", "Access token obtained for reading chats")
            return self.access_token
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                AvitoLogger.log("error", "Invalid credentials (401)")
                self.stats['last_error'] = "Invalid credentials"
                raise
            else:
                error_msg = f"Error getting access token: {e}"
                AvitoLogger.log("error", error_msg)
                self.stats['last_error'] = error_msg
                raise
    
    def get_chats(self, unread_only=False, limit=None, offset=0):
        """
        Retrieves list of chats.
        
        :param unread_only: Only get unread chats
        :param limit: Limit number of chats
        :param offset: Offset for pagination
        :return: Chat data
        """
        try:
            token = self.get_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            
            params = {
                "limit": limit or BATCH_SIZE,
                "offset": offset
            }
            
            if unread_only:
                params["unread_only"] = "true"
            
            url = AVITO_CHATS_URL_TEMPLATE.format(user_id=self.user_id)
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            chats_data = response.json()
            processed_data = self._process_timestamps(chats_data)
            
            AvitoLogger.log("debug", f"Retrieved {len(processed_data.get('chats', []))} chats")
            return processed_data
                
        except Exception as e:
            error_msg = f"Error getting chats: {e}"
            AvitoLogger.log("error", error_msg)
            self.stats['last_error'] = error_msg
            return {"chats": []}
    
    def _process_timestamps(self, data):
        """
        Recursively processes all timestamp fields in API response.
        """
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if isinstance(value, (int, float)) and 1_000_000_000 < value < 2_000_000_000:
                    try:
                        dt = datetime.datetime.fromtimestamp(value)
                        result[key] = value
                        result[f"{key}_formatted"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        result[f"{key}_human"] = dt.strftime("%d.%m.%Y at %H:%M")
                        result[f"{key}_datetime"] = dt
                    except (ValueError, OSError):
                        result[key] = value
                elif isinstance(value, (dict, list)):
                    result[key] = self._process_timestamps(value)
                else:
                    result[key] = value
            return result
            
        elif isinstance(data, list):
            return [self._process_timestamps(item) for item in data]
        
        return data
    
    def get_unread_messages(self):
        """
        Gets all unread messages from chats with user names.
        
        :return: List of unread messages with user info
        """
        try:
            chats_data = self.get_chats(unread_only=False)
            chats = chats_data.get('chats', [])
            
            unread_messages = []
            user_names_seen = set()
            
            AvitoLogger.log("debug", f"Checking {len(chats)} chats for unread messages")
            
            for chat in chats:
                chat_id = str(chat.get('id'))
                if not chat_id:
                    continue
                
                # Extract user name
                user_name = extract_user_name(chat)
                
                # Check last message
                if 'last_message' in chat and chat['last_message']:
                    msg = chat['last_message']
                    
                    # Get message ID - this is the key identifier!
                    message_id = str(msg.get('id'))
                    if not message_id:
                        AvitoLogger.log("warning", f"Message has no ID in chat {chat_id}")
                        continue
                    
                    # Check if message is unread and incoming
                    is_unread = not msg.get('read', False)
                    is_incoming = msg.get('direction') == 'in'
                    
                    if is_unread and is_incoming:
                        message_text = msg.get('content', {}).get('text', '')
                        
                        # Check if this is a system message
                        is_system = is_system_message(message_text)
                        
                        # Check if we've already processed this message by ID (not by text!)
                        if message_id not in self.processed_message_ids:
                            message_data = {
                                'chat_id': chat_id,
                                'message_id': message_id,
                                'text': message_text,
                                'created': msg.get('created_formatted', ''),
                                'created_timestamp': msg.get('created', 0),
                                'direction': 'in',
                                'is_unread': True,
                                'is_system': is_system,
                                'user_name': user_name
                            }
                            
                            unread_messages.append(message_data)
                            
                            # Add to processed messages
                            self.processed_message_ids.add(message_id)
                            AvitoLogger.log("debug", f"New message detected: ID={message_id[:8]}..., user={user_name}, system={is_system}")
                            
                            # Track user names for statistics
                            if user_name not in user_names_seen:
                                user_names_seen.add(user_name)
                                self.stats['last_user_names'].append({
                                    'name': user_name,
                                    'time': datetime.datetime.now().isoformat(),
                                    'is_system': is_system
                                })
                                # Keep only last 20 user names
                                if len(self.stats['last_user_names']) > 20:
                                    self.stats['last_user_names'] = self.stats['last_user_names'][-20:]
                        else:
                            AvitoLogger.log("debug", f"Message {message_id[:8]}... already processed, skipping")
            
            # Save processed IDs if we found new messages
            if unread_messages:
                self._save_processed_ids()
                AvitoLogger.log("info", f"Found {len(unread_messages)} new unread messages")
            else:
                AvitoLogger.log("debug", "No new unread messages found")
            
            return unread_messages
            
        except Exception as e:
            error_msg = f"Error getting unread messages: {e}"
            AvitoLogger.log("error", error_msg)
            self.stats['last_error'] = error_msg
            return []
    
    def get_all_chats(self):
        """
        Gets all chats (not just unread) with user names.
        
        :return: Chat data with user names
        """
        all_chats = []
        offset = 0
        
        try:
            while True:
                batch = self.get_chats(limit=BATCH_SIZE, offset=offset)
                chats = batch.get('chats', [])
                
                if not chats:
                    break
                
                # Add user names to each chat
                for chat in chats:
                    chat['user_name'] = extract_user_name(chat)
                    all_chats.append(chat)
                
                if len(all_chats) >= MAX_CHATS:
                    all_chats = all_chats[:MAX_CHATS]
                    break
                
                if len(chats) < BATCH_SIZE:
                    break
                
                offset += BATCH_SIZE
                
        except Exception as e:
            error_msg = f"Error in pagination: {e}"
            AvitoLogger.log("error", error_msg)
            self.stats['last_error'] = error_msg
        
        processed_chats = self._process_timestamps(all_chats)
        
        result = {
            'total_chats': len(processed_chats),
            'chats': processed_chats,
            'retrieved_at': datetime.datetime.now().isoformat(),
            'retrieved_at_formatted': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        AvitoLogger.log("info", f"Retrieved {result['total_chats']} total chats")
        return result
    
    def check_for_updates(self):
        """
        Main update check function.
        
        :return: Tuple of (chat_data, unread_messages, auto_reply_results)
        """
        self.stats['total_checks'] += 1
        self.stats['last_check'] = datetime.datetime.now().isoformat()
        
        AvitoLogger.log("info", f"Check #{self.stats['total_checks']} started")
        
        try:
            # Step 1: Get unread messages (using message ID comparison)
            unread_messages = self.get_unread_messages()
            
            # Separate system and regular messages
            system_messages = [msg for msg in unread_messages if msg.get('is_system', False)]
            regular_messages = [msg for msg in unread_messages if not msg.get('is_system', False)]
            
            # Update statistics
            self.stats['total_unread_messages'] += len(unread_messages)
            self.stats['total_system_messages'] += len(system_messages)
            self.stats['total_regular_messages'] += len(regular_messages)
            self.stats['last_unread_count'] = len(unread_messages)
            
            # Log notifications for ALL messages
            if unread_messages:
                AvitoLogger.log("info", f"📨 Found {len(unread_messages)} new message(s)")
                AvitoLogger.log("info", f"  - Regular messages: {len(regular_messages)}")
                AvitoLogger.log("info", f"  - System messages: {len(system_messages)}")
                
                for msg in unread_messages[:3]:  # Log first 3 messages
                    user_name = msg.get('user_name', 'Unknown User')
                    is_system = msg.get('is_system', False)
                    message_type = "SYSTEM" if is_system else "USER"
                    message_id_short = msg.get('message_id', '')[:8]
                    AvitoLogger.log("info", 
                                   f"  {message_type} message from {user_name} (ID: {message_id_short}...): {msg['text'][:50]}...",
                                   message_id=msg['message_id'],
                                   system=is_system)
            else:
                AvitoLogger.log("info", "No new messages found in this check")
            
            # Step 2: Process auto-replies only for regular messages
            auto_reply_results = []
            if self.auto_reply_enabled and regular_messages:
                auto_reply_results = self.auto_reply_manager.process_auto_replies(unread_messages)
                self.stats['total_auto_replies'] += len(auto_reply_results)
            
            # Step 3: Get all chats for saving
            all_chats = self.get_all_chats()
            
            # Save to file
            try:
                with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
                    json.dump(all_chats, f, ensure_ascii=False, indent=2, default=str)
                AvitoLogger.log("info", f"Saved {all_chats['total_chats']} chats to {JSON_FILENAME}")
            except Exception as e:
                error_msg = f"Error saving to file: {e}"
                AvitoLogger.log("error", error_msg)
                self.stats['last_error'] = error_msg
            
            # Clear last error if successful
            self.stats['last_error'] = None
            
            return all_chats, unread_messages, auto_reply_results
            
        except Exception as e:
            error_msg = f"Error in check_for_updates: {e}"
            AvitoLogger.log("error", error_msg)
            self.stats['last_error'] = error_msg
            return {"chats": []}, [], []
    
    def get_statistics(self):
        """
        Returns current statistics.
        
        :return: Dictionary with statistics
        """
        stats = self.stats.copy()
        stats['current_time'] = datetime.datetime.now().isoformat()
        
        # Calculate uptime
        try:
            start_time = datetime.datetime.fromisoformat(stats['start_time'])
            uptime_delta = datetime.datetime.now() - start_time
            stats['uptime'] = str(uptime_delta).split('.')[0]  # Remove microseconds
        except:
            stats['uptime'] = "0:00:00"
        
        # Add file info
        try:
            if JSON_FILENAME.exists():
                file_stats = JSON_FILENAME.stat()
                stats['file_info'] = {
                    'size_kb': round(file_stats.st_size / 1024, 2),
                    'modified': datetime.datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                }
        except Exception as e:
            AvitoLogger.log("debug", f"Error getting file stats: {e}")
        
        # Add processed IDs count
        stats['processed_message_ids_count'] = len(self.processed_message_ids)
        
        # Add recent user activity
        recent_users = []
        for user_info in self.stats.get('last_user_names', [])[-5:]:  # Last 5 users
            if isinstance(user_info, dict):
                recent_users.append({
                    'name': user_info.get('name', 'Unknown'),
                    'time': user_info.get('time', ''),
                    'system': user_info.get('is_system', False)
                })
        
        stats['recent_users'] = recent_users
        
        return stats

def get_recent_messages(limit=20, level_filter=None):
    """
    Get recent messages/errors for web interface.
    
    :param limit: Maximum number of messages to return
    :param level_filter: Filter by level (info, warning, error, etc.)
    :return: List of recent messages
    """
    try:
        messages_file = LOG_DIR / "messages.json"
        if messages_file.exists():
            with open(messages_file, 'r', encoding='utf-8') as f:
                messages = json.load(f)
                if isinstance(messages, list):
                    if level_filter:
                        messages = [m for m in messages if m.get('type') == level_filter]
                    return messages[-limit:]  # Return most recent messages
    except Exception as e:
        AvitoLogger.log("error", f"Error reading message logs: {e}")
    
    return []

def get_recent_notifications(limit=10):
    """
    Get recent notifications (new messages from users).
    
    :param limit: Maximum number of notifications
    :return: List of notifications
    """
    try:
        # We can extract notifications from logs or store separately
        messages = get_recent_messages(limit=limit * 2)  # Get more to filter
        
        notifications = []
        for msg in messages:
            message_text = msg.get('message', '')
            # Look for notification patterns
            if ('new message' in message_text.lower() or 
                'found' in message_text.lower() and 'message' in message_text.lower()):
                notifications.append(msg)
        
        return notifications[:limit]
    except Exception as e:
        AvitoLogger.log("error", f"Error getting notifications: {e}")
        return []