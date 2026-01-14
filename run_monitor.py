#!/usr/bin/env python3
"""
Standalone script to run Avito Chat Monitor
"""
import sys
import os
import signal
import time
from avito_api import AvitoLogger, AvitoChatMonitor

def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    print("\n\n🛑 Received shutdown signal. Stopping monitor...")
    sys.exit(0)

def main():
    """Main function for standalone execution"""
    # Setup logging
    logger = AvitoLogger.setup_logging()
    
    print("🚀 Starting Avito Chat Monitor (Standalone Mode)")
    print("=" * 60)
    
    try:
        # Create monitor instance
        monitor = AvitoChatMonitor()
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Run continuous monitoring
        monitor.run_continuous_monitoring()
        
    except Exception as e:
        logger.error(f"Fatal error in monitor: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())