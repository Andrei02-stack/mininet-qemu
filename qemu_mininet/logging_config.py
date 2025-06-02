import os
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

# Get current timestamp for log file name
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = os.path.join(LOGS_DIR, f'mininet_{timestamp}.log')

# Configure root logger
def setup_logging():
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    simple_formatter = logging.Formatter('%(message)s')

    # Create file handler for detailed logs
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # Create console handler for user-friendly output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Create a logger for detailed system logs
    system_logger = logging.getLogger('system')
    system_logger.setLevel(logging.DEBUG)
    system_logger.addHandler(file_handler)

    return root_logger, system_logger

# Create logger instances
root_logger, system_logger = setup_logging()

def info(msg):
    """User-friendly info message (console only)"""
    root_logger.info(msg)

def debug(msg):
    """Detailed debug message (log file only)"""
    system_logger.debug(msg)

def error(msg):
    """Error message (both console and log file)"""
    root_logger.error(msg)
    system_logger.error(msg)

def warning(msg):
    """Warning message (both console and log file)"""
    root_logger.warning(msg)
    system_logger.warning(msg) 