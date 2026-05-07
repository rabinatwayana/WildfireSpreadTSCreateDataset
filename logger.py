import os
import time
import traceback
from datetime import datetime
from contextlib import contextmanager

# =========================================
# Project Logger
# =========================================
class CustomLogger:
    """
    A simple project logger for tracking messages and timing code execution steps.
    Purpose:
        - Log messages with timestamps
        - Track execution time of code blocks using `step` context manager
        - Store logs in memory for optional inspection or saving
    Example:
        logger = CustomLogger()
        logger.log("Starting experiment")
        
        with logger.step("Data Loading"):
            load_data()
        with logger.step("Training"):
            train_model()
    """
    

    def __init__(self):
        self.logs = []
    
    def log(self, msg: str):
        """
        Log a message with the current UTC timestamp.
        Args:
            msg (str): The message to log.
        Returns:
            Prints the log message to the console.
            Stores the log message in self.logs.
        """
        
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        self.logs.append(line)
        print(line)
    
    def clear(self):
        self.logs = []

    def log_exception(self, prefix: str, exc: Exception = None):
        """
        Log an exception message and traceback.
        Args:
            prefix (str): Context message describing where the failure happened.
            exc (Exception, optional): Exception object. If omitted, uses current traceback.
        """
        if exc is not None:
            self.log(f"{prefix}: {type(exc).__name__}: {exc}")
        else:
            self.log(prefix)
        tb = traceback.format_exc().strip()
        if tb and tb != "NoneType: None":
            for line in tb.splitlines():
                self.log(line)

    @staticmethod
    def format_execution_time(seconds: float) -> str:
        """
        Convert a time in seconds into a human-readable string.
        Args:
            seconds (float): Time in seconds.
        Returns:
            str: Formatted time, e.g., "2.34s", "3.12m", "1.25h"
        """
        
        if seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.2f}m"
        else:
            return f"{seconds / 3600:.2f}h"

    @contextmanager
    def step(self, name: str):
        """
        Context manager to log the start and end of a code block, including execution time.

        This allows you to wrap any block of code with `with logger.step("Step Name"):` 
        to automatically log when it starts and ends, along with the formatted duration.
        Args:
            name (str): A descriptive name for the step being tracked.
        Usage:
            with logger.step("Training model"):
                train_model()
        Notes:
            - Execution time is formatted automatically in seconds, minutes, or hours.
            - Logs are stored in self.logs and printed to the console.
        """
        
        self.log(f"START: {name}")
        start = time.perf_counter()
        try:
            yield
        except Exception as exc:
            self.log_exception(f"FAILED: {name}", exc)
            raise
        finally:
            end = time.perf_counter()
            elapsed = end - start
            self.log(f"END: {name} (Duration: {self.format_execution_time(elapsed)})")


    def save(self, log_save_path):
        """
        Save the accumulated logs to a local file.
        Args:
            log_save_path (str): Full path specifying where and under what name the log file will be saved (e.g., 'output/experiment.log')
        Behavior:
            - Creates a 'logs' folder if it does not exist.
            - Writes all messages stored in self.logs to the specified file.
            - Prints confirmation or error message.
        Example:
            logger.save(output_dir="logs", filename="run1.log")
        """
        
        try:
            os.makedirs("logs", exist_ok=True)
            with open(log_save_path, "w") as f:
                f.write("\n".join(self.logs))
            print(f"Log saved locally: {log_save_path}")
        except Exception as e:
            print(f"Failed to save logs to local: {e}")
