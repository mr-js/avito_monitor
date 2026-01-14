"""
Monitor Service for running in background thread
"""
import threading
import time
import logging
import json
import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from avito_api import AvitoChatMonitor, AvitoLogger, get_recent_messages

logger = logging.getLogger(__name__)

class MonitorService:
    """
    Service wrapper for running AvitoChatMonitor in a background thread.
    """
    
    def __init__(self, auto_reply_enabled=None):
        self.monitor = None
        self.thread = None
        self.running = False
        self.auto_reply_enabled = auto_reply_enabled
        self.interval = None
        
        # Statistics
        self.service_stats = {
            'service_created': datetime.datetime.now().isoformat(),
            'last_error': None,
            'thread_alive': False,
            'start_attempts': 0,
            'last_start_attempt': None,
            'total_cycles': 0,
            'successful_cycles': 0,
            'failed_cycles': 0
        }
        
        # Initialize monitor (but don't start thread yet)
        self._init_monitor()
    
    def _init_monitor(self):
        """Initialize the monitor instance"""
        try:
            self.monitor = AvitoChatMonitor(auto_reply_enabled=self.auto_reply_enabled)
            logger.info("Monitor instance initialized successfully")
            return True
        except Exception as e:
            error_msg = f"Failed to initialize monitor: {e}"
            logger.error(error_msg)
            self.service_stats['last_error'] = error_msg
            return False
    
    def start(self, interval=30):
        """
        Start the monitoring service in a background thread.
        
        :param interval: Check interval in seconds
        :return: True if started successfully
        """
        if self.running:
            logger.warning("Service is already running")
            return True
        
        self.service_stats['start_attempts'] += 1
        self.service_stats['last_start_attempt'] = datetime.datetime.now().isoformat()
        
        try:
            # Ensure monitor is initialized
            if self.monitor is None:
                if not self._init_monitor():
                    logger.error("Cannot start: monitor initialization failed")
                    return False
            
            self.interval = interval
            
            # Create and start thread
            self.thread = threading.Thread(
                target=self._run_monitoring_loop,
                args=(interval,),
                daemon=True,
                name="AvitoMonitorThread"
            )
            
            self.running = True
            self.service_stats['thread_alive'] = True
            
            self.thread.start()
            
            logger.info(f"Monitor service started successfully with {interval}s interval")
            logger.info(f"Auto-reply: {'ENABLED' if self.auto_reply_enabled else 'DISABLED'}")
            
            # Log start event
            AvitoLogger.log("info", f"🚀 Monitoring service started (interval: {interval}s)")
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to start monitor service: {e}"
            logger.error(error_msg)
            self.service_stats['last_error'] = error_msg
            AvitoLogger.log("error", f"Failed to start service: {e}")
            return False
    
    def _run_monitoring_loop(self, interval):
        """
        Internal method to run monitoring in thread.
        """
        logger.info(f"Monitoring thread started with {interval}s interval")
        
        cycle_count = 0
        
        try:
            while self.running:
                cycle_count += 1
                self.service_stats['total_cycles'] += 1
                
                try:
                    # Perform check
                    if self.monitor:
                        start_time = time.time()
                        
                        logger.debug(f"Cycle #{cycle_count}: Starting check...")
                        result = self.monitor.check_for_updates()
                        
                        elapsed = time.time() - start_time
                        self.service_stats['successful_cycles'] += 1
                        
                        # Log successful check
                        if result and len(result) >= 2:
                            unread_messages = result[1] if len(result) > 1 else []
                            if unread_messages:
                                logger.info(f"Cycle #{cycle_count}: Found {len(unread_messages)} new message(s) in {elapsed:.1f}s")
                            else:
                                logger.debug(f"Cycle #{cycle_count}: No new messages in {elapsed:.1f}s")
                        
                    else:
                        logger.error("Monitor instance is None, attempting to reinitialize...")
                        if not self._init_monitor():
                            logger.error("Failed to reinitialize monitor")
                            self.service_stats['failed_cycles'] += 1
                
                except Exception as e:
                    error_msg = f"Error in monitoring cycle #{cycle_count}: {e}"
                    logger.error(error_msg)
                    self.service_stats['last_error'] = error_msg
                    self.service_stats['failed_cycles'] += 1
                    AvitoLogger.log("error", f"Monitoring cycle error: {e}")
                
                # Calculate sleep time (adjust based on activity)
                sleep_time = interval
                if self.monitor and hasattr(self.monitor, 'stats'):
                    last_unread = self.monitor.stats.get('last_unread_count', 0)
                    if last_unread > 0:
                        # Check more frequently if we just got messages
                        sleep_time = max(10, interval // 2)
                
                # Sleep until next cycle
                for i in range(int(sleep_time)):
                    if not self.running:
                        break
                    time.sleep(1)
        
        except Exception as e:
            error_msg = f"Fatal error in monitoring thread: {e}"
            logger.error(error_msg)
            self.service_stats['last_error'] = error_msg
            AvitoLogger.log("error", f"Monitoring thread crashed: {e}")
        
        finally:
            self.running = False
            self.service_stats['thread_alive'] = False
            logger.info(f"Monitoring thread stopped after {cycle_count} cycles")
    
    def stop(self):
        """
        Stop the monitoring service.
        """
        if not self.running:
            logger.info("Service is not running")
            return
        
        logger.info("Stopping monitor service...")
        self.running = False
        
        # Wait for thread to finish (with timeout)
        if self.thread and self.thread.is_alive():
            logger.info("Waiting for thread to finish...")
            self.thread.join(timeout=10)
            
            if self.thread.is_alive():
                logger.warning("Thread did not stop gracefully")
            else:
                logger.info("Thread stopped successfully")
        
        AvitoLogger.log("info", "🛑 Monitoring service stopped")
        
        # Update stats
        self.service_stats['thread_alive'] = False
    
    def check_now(self):
        """
        Perform an immediate check (if monitor is initialized).
        
        :return: Check results or None
        """
        if not self.monitor:
            logger.warning("Monitor not initialized for check_now")
            # Try to initialize
            if not self._init_monitor():
                logger.error("Failed to initialize monitor for check_now")
                return None
        
        try:
            logger.info("Performing immediate check...")
            result = self.monitor.check_for_updates()
            
            # Log the result
            if result and len(result) >= 2:
                unread_messages = result[1] if len(result) > 1 else []
                logger.info(f"Immediate check: Found {len(unread_messages)} new message(s)")
            
            return result
            
        except Exception as e:
            error_msg = f"Error in immediate check: {e}"
            logger.error(error_msg)
            self.service_stats['last_error'] = error_msg
            AvitoLogger.log("error", f"Immediate check failed: {e}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current service status.
        
        :return: Dictionary with status information
        """
        status = {
            'running': self.running,
            'interval': self.interval,
            'auto_reply_enabled': self.auto_reply_enabled,
            'service_stats': self.service_stats.copy()
        }
        
        # Add thread info
        if self.thread:
            status['thread_info'] = {
                'name': self.thread.name,
                'ident': self.thread.ident,
                'daemon': self.thread.daemon,
                'is_alive': self.thread.is_alive()
            }
        
        # Add monitor stats if available
        if self.monitor:
            try:
                monitor_stats = self.monitor.get_statistics()
                status['monitor_stats'] = monitor_stats
                
                # Calculate uptime
                if 'start_time' in monitor_stats:
                    try:
                        start_time = datetime.datetime.fromisoformat(monitor_stats['start_time'])
                        uptime = datetime.datetime.now() - start_time
                        status['monitor_uptime'] = str(uptime).split('.')[0]
                    except:
                        status['monitor_uptime'] = "Unknown"
                
                # Add recent notifications
                status['recent_notifications'] = get_recent_messages(limit=5)
                
            except Exception as e:
                logger.error(f"Error getting monitor stats: {e}")
                status['monitor_stats_error'] = str(e)
        
        return status

# Global service instance
_service_instance: Optional[MonitorService] = None

def get_monitor_service(auto_reply_enabled=None) -> MonitorService:
    """
    Get or create singleton monitor service instance.
    
    :param auto_reply_enabled: Override auto-reply setting
    :return: MonitorService instance
    """
    global _service_instance
    
    if _service_instance is None:
        logger.info(f"Creating new MonitorService instance (auto_reply: {auto_reply_enabled})")
        _service_instance = MonitorService(auto_reply_enabled=auto_reply_enabled)
    
    return _service_instance

def start_service(interval=30, auto_reply_enabled=None):
    """
    Start the monitor service.
    
    :param interval: Check interval in seconds
    :param auto_reply_enabled: Override auto-reply setting
    :return: True if started successfully
    """
    logger.info(f"Starting service with interval={interval}s, auto_reply={auto_reply_enabled}")
    
    service = get_monitor_service(auto_reply_enabled)
    
    # Update auto-reply setting if provided
    if auto_reply_enabled is not None:
        service.auto_reply_enabled = auto_reply_enabled
        if service.monitor:
            service.monitor.auto_reply_enabled = auto_reply_enabled
    
    return service.start(interval)

def stop_service():
    """
    Stop the monitor service.
    """
    global _service_instance
    
    logger.info("Stopping monitor service...")
    
    if _service_instance:
        _service_instance.stop()
        # Don't set to None, keep instance for potential restart
        return True
    
    logger.warning("No service instance to stop")
    return False

def get_service_status() -> Optional[Dict]:
    """
    Get current service status.
    
    :return: Status dictionary or None if service not created
    """
    if _service_instance:
        return _service_instance.get_status()
    
    # Return minimal status if no instance
    return {
        'running': False,
        'service_stats': {
            'service_created': datetime.datetime.now().isoformat(),
            'thread_alive': False,
            'status': 'No service instance'
        }
    }