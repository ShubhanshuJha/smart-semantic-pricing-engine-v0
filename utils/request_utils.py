import requests
from .operation_utils import retry



class RequestUtils:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        }
    
    @retry(retries=3, delay=0)
    def get_data(self, url, timeout: int = 20):
        response = requests.get(url, headers=self.headers, timeout=timeout)
        if response.status_code != 200:
            raise Exception(f"Invalid Response -- {response.status_code = }")
        return response
    


