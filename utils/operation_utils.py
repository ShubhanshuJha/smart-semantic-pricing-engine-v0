import functools
import time
import yaml, json
from pathlib import Path
import os


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

def write_data(path, data, mode='w', encoding="utf-8"):
    with open(path, mode=mode, encoding=encoding) as f:
        return f.write(data)

@retry(retries=2, delay=1)
def write_json_data(data: list[dict], path: str, mode='w'):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if mode in ['a', 'a+'] and os.path.exists(path):
        with open(out_path, 'r') as file:
            stored_data = json.load(file)
        stored_data.extend(data)
        data = stored_data
        # print(f"(*) New data size: {len(data)}")
    write_data(path=out_path, data=json.dumps(data, indent=4, ensure_ascii=False), mode='w')
    return out_path

