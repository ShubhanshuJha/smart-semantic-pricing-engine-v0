import functools
import time
import yaml
from pathlib import Path


def retry(retries=3, delay=0, exceptions=(Exception,)):
    """
    Retry decorator.
    Args:
        retries (int): Number of times to retry before giving up.
        delay (int/float): Seconds to wait between retries.
        exceptions (tuple): Exception classes to catch and retry on.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries_limit = kwargs.pop("retries", retries)
            interval = kwargs.pop("delay", delay)
            attempts = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempts += 1
                    if attempts > retries_limit:
                        raise
                    if delay:
                        time.sleep(interval)
        return wrapper
    return decorator



def load_yaml_config(path: str):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))

