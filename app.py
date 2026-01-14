"""
Flask Web Application for Avito Chat Monitor
"""
from flask import Flask, jsonify, render_template, request
import json
import datetime
from pathlib import Path
from monitor_service import get_monitor_service, start_service, stop_service, get_service_status
from avito_api import AvitoLogger, get_recent_messages
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# Ensure directories exist
Path('templates').mkdir(exist_ok=True)
Path('static').mkdir(exist_ok=True)

# Configuration
try:
    from config import (
        JSON_FILENAME, CHECK_INTERVAL, AUTO_REPLY_ENABLED, 
        AUTO_REPLY_MESSAGE, AUTO_START_MONITOR
    )
except ImportError:
    JSON_FILENAME = "avito_chats.json"
    CHECK_INTERVAL = 30
    AUTO_REPLY_ENABLED = True
    AUTO_REPLY_MESSAGE = "Напишите мне в Telegram для быстрого ответа: @mr0js"
    AUTO_START_MONITOR = True

# Initialize service when module loads (before any requests)
logger.info("Initializing monitor service on module load...")
service = get_monitor_service()

if AUTO_START_MONITOR and not service.running:
    try:
        logger.info("Auto-starting monitor service...")
        if service.start(interval=CHECK_INTERVAL):
            logger.info("Auto-start successful")
            AvitoLogger.log("info", "🔄 Service auto-started on module load")
        else:
            logger.error("Auto-start failed")
    except Exception as e:
        logger.error(f"Failed to auto-start monitor: {e}")

@app.route('/')
def index():
    """Main page with monitoring dashboard"""
    service_status = get_service_status() or {}
    chats_data = load_chats_data()
    
    # Get recent notifications/messages
    recent_messages = get_recent_messages(limit=10)
    
    return render_template('index.html', 
                         service_status=service_status,
                         chats_data=chats_data,
                         check_interval=CHECK_INTERVAL,
                         auto_reply_enabled=AUTO_REPLY_ENABLED,
                         auto_reply_message=AUTO_REPLY_MESSAGE,
                         recent_messages=recent_messages)

@app.route('/api/status')
def api_status():
    """API endpoint for service status"""
    status = get_service_status() or {}
    return jsonify(status)

@app.route('/api/start', methods=['POST'])
def api_start():
    """API endpoint to start monitoring service"""
    try:
        # Get data from form or JSON
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict() or {}
        
        interval = data.get('interval', CHECK_INTERVAL)
        
        # Convert string values
        try:
            interval = float(interval)
        except:
            interval = CHECK_INTERVAL
        
        logger.info(f"API request to start service with interval={interval}")
        
        success = start_service(interval=interval)
        
        if success:
            logger.info("Service started successfully via API")
            AvitoLogger.log("info", f"✅ Service started via web interface (interval: {interval}s)")
        else:
            logger.error("Failed to start service via API")
        
        return jsonify({
            'success': success,
            'message': 'Service started successfully' if success else 'Failed to start service'
        })
    except Exception as e:
        error_msg = f"Error starting service: {e}"
        logger.error(error_msg)
        AvitoLogger.log("error", f"Web interface start failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """API endpoint to stop monitoring service"""
    try:
        stop_service()
        logger.info("Service stopped via API")
        AvitoLogger.log("info", "🛑 Service stopped via web interface")
        return jsonify({
            'success': True,
            'message': 'Service stopped'
        })
    except Exception as e:
        logger.error(f"Error stopping service: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/check-now', methods=['POST'])
def api_check_now():
    """API endpoint to perform immediate check"""
    try:
        service = get_monitor_service()
        
        if service and hasattr(service, 'check_now'):
            result = service.check_now()
            
            if result and isinstance(result, tuple) and len(result) >= 2:
                unread_messages = result[1] if len(result) > 1 else []
                unread_count = len(unread_messages) if isinstance(unread_messages, list) else 0
                
                # Log detailed info
                logger.info(f"Immediate check found {unread_count} messages")
                
                if unread_count > 0:
                    for i, msg in enumerate(unread_messages[:3]):
                        msg_id = msg.get('message_id', '')[:8]
                        user_name = msg.get('user_name', 'Unknown')
                        is_system = msg.get('is_system', False)
                        msg_type = "SYSTEM" if is_system else "USER"
                        text_preview = msg.get('text', '')[:50]
                        logger.info(f"  {i+1}. {msg_type} from {user_name} (ID: {msg_id}...): {text_preview}...")
                
                message = f'Check completed. Found {unread_count} new message(s).'
                AvitoLogger.log("info", f"Immediate check: Found {unread_count} new message(s)")
            else:
                message = 'Check completed (no new messages)'
                logger.info("Immediate check: No new messages found")
            
            return jsonify({
                'success': True,
                'message': message,
                'result': 'Check completed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Service not available'
            }), 400
        
    except Exception as e:
        logger.error(f"Error in immediate check: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/reset-processed-ids', methods=['POST'])
def api_reset_processed_ids():
    """API endpoint to reset processed message IDs (for testing)"""
    try:
        service = get_monitor_service()
        
        if service and hasattr(service, 'monitor'):
            # Reset processed IDs
            service.monitor.reset_processed_ids()
            
            logger.info("Processed message IDs reset")
            AvitoLogger.log("info", "🔄 Processed message IDs reset")
            
            return jsonify({
                'success': True,
                'message': 'Processed message IDs reset successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Service not available'
            }), 400
        
    except Exception as e:
        logger.error(f"Error resetting processed IDs: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/chats')
def api_chats():
    """API endpoint to get recent chats"""
    try:
        chats_data = load_chats_data()
        
        # Limit number of chats for API response
        limit = min(int(request.args.get('limit', 50)), 100)
        chats = chats_data.get('chats', [])[:limit]
        
        # Format chats for display
        formatted_chats = []
        for chat in chats:
            formatted_chat = chat.copy()
            # Use user_name if available
            if 'user_name' in chat:
                formatted_chat['display_name'] = chat['user_name']
            else:
                # Extract from chat ID as fallback
                chat_id = str(chat.get('id', ''))
                if len(chat_id) > 10:
                    formatted_chat['display_name'] = f"User_{chat_id[-8:]}"
                else:
                    formatted_chat['display_name'] = "Unknown User"
            
            formatted_chats.append(formatted_chat)
        
        return jsonify({
            'success': True,
            'total_chats': len(chats_data.get('chats', [])),
            'chats': formatted_chats,
            'last_updated': chats_data.get('retrieved_at_formatted', 'Never')
        })
    except Exception as e:
        logger.error(f"Error loading chats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint to get statistics"""
    try:
        service = get_monitor_service()
        stats = {}
        
        if service and hasattr(service, 'monitor') and service.monitor:
            stats = service.monitor.get_statistics()
        else:
            stats = {
                'service_status': 'Not initialized',
                'start_time': datetime.datetime.now().isoformat(),
                'total_checks': 0,
                'total_unread_messages': 0,
                'total_auto_replies': 0,
                'total_system_messages': 0,
                'total_regular_messages': 0
            }
        
        # Add file info
        json_file = Path(JSON_FILENAME)
        if json_file.exists():
            try:
                file_stats = json_file.stat()
                stats['file_info'] = {
                    'size_kb': round(file_stats.st_size / 1024, 2),
                    'modified': datetime.datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                }
            except:
                pass
        
        # Add recent messages as notifications
        stats['recent_notifications'] = get_recent_messages(limit=10)
        
        # Add service running status
        if service:
            stats['service_running'] = service.running
            stats['service_stats'] = service.service_stats
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/notifications')
def api_notifications():
    """API endpoint to get recent notifications"""
    try:
        limit = min(int(request.args.get('limit', 10)), 50)
        messages = get_recent_messages(limit=limit)
        
        # Filter for notification-like messages
        notifications = []
        for msg in messages:
            message_text = msg.get('message', '').lower()
            # Include messages about new messages, errors, warnings, starts/stops
            if any(keyword in message_text for keyword in 
                   ['new message', 'found', 'error', 'warning', 'started', 'stopped', 'check']):
                notifications.append(msg)
        
        return jsonify({
            'success': True,
            'notifications': notifications[:limit],
            'count': len(notifications)
        })
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/messages')
def api_messages():
    """API endpoint to get all recent messages"""
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
        level_filter = request.args.get('level')
        
        messages = get_recent_messages(limit=limit)
        
        if level_filter:
            messages = [m for m in messages if m.get('level', '').lower() == level_filter.lower()]
        
        return jsonify({
            'success': True,
            'messages': messages,
            'count': len(messages)
        })
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config')
def api_config():
    """API endpoint to get configuration"""
    try:
        config = {
            'auto_reply_enabled': AUTO_REPLY_ENABLED,
            'auto_reply_message': AUTO_REPLY_MESSAGE,
            'check_interval': CHECK_INTERVAL,
            'auto_start_monitor': AUTO_START_MONITOR
        }
        
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def load_chats_data():
    """Load chats data from JSON file"""
    try:
        json_file = Path(JSON_FILENAME)
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Ensure required fields exist
                if 'chats' not in data:
                    data['chats'] = []
                if 'total_chats' not in data:
                    data['total_chats'] = len(data.get('chats', []))
                
                # Add display names if not present
                for chat in data.get('chats', []):
                    if 'user_name' not in chat:
                        # Extract user name from available data
                        chat_id = str(chat.get('id', ''))
                        if len(chat_id) > 10:
                            chat['user_name'] = f"User_{chat_id[-8:]}"
                        else:
                            chat['user_name'] = "Unknown User"
                
                return data
    except Exception as e:
        logger.error(f"Error loading chats data: {e}")
    
    # Return empty structure if file doesn't exist or error
    return {
        "chats": [],
        "total_chats": 0,
        "retrieved_at_formatted": "Never"
    }

if __name__ == '__main__':
    # Setup logging
    AvitoLogger.setup_logging()
    
    logger.info("=" * 60)
    logger.info("🚀 Starting Avito Chat Monitor Web Interface")
    logger.info(f"📊 Auto-reply: {'ENABLED ✅' if AUTO_REPLY_ENABLED else 'DISABLED ❌'}")
    logger.info(f"💬 Auto-reply message: {AUTO_REPLY_MESSAGE}")
    logger.info(f"⏱️  Auto-start monitor: {'ENABLED ✅' if AUTO_START_MONITOR else 'DISABLED ❌'}")
    logger.info(f"🔄 Check interval: {CHECK_INTERVAL} seconds")
    logger.info("=" * 60)
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)