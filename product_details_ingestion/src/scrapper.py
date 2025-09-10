import time
import random
from urllib.parse import urlparse, urljoin
from sys import path as sys_path
from os import path as os_path, listdir
from xml.etree import ElementTree as ET

sys_path.append(os_path.realpath('../../'))
sys_path.append(os_path.realpath('../'))
sys_path.append(os_path.realpath('./'))

from utils.operation_utils import load_yaml_config
from utils.request_utils import RequestUtils


class Scrapper:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.request = RequestUtils()
        self.retry_count = int(config.get("retry_count", "3"))
    
    def __get_delay(self):
        return random.uniform(self.config["rate_limit_seconds"][0], self.config["rate_limit_seconds"][1])
    
    def __delay(self):
        time.sleep(self.__get_delay())

    def __get_urls_from_sitemap(self, sitemap_url: str) -> list[str]:
        self.__delay()
        response = self.request.get_data(
            url=sitemap_url,
            retries=self.retry_count,
            delay=self.__get_delay()
        )
        urls = []
        if response and response.status_code == 200:
            try:
                root = ET.fromstring(response.content)
                sitemap_index = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap")
                if sitemap_index:
                    for sitemap in sitemap_index:
                        loc = sitemap.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                        if loc is not None:
                            child_urls = self.__get_urls_from_sitemap(loc.text) or []
                            urls.extend(child_urls)
                else:
                    url_locs = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                    urls.extend([elem.text for elem in url_locs if elem is not None])
            except ET.ParseError as e:
                print(f"[WARN] Failed to parse sitemap {sitemap_url}: {e}")
        return urls   # <- Always a list
        
    def __locate_product_sitemaps(self):
        robots_url = urljoin(self.config["url"], "/robots.txt")
        print(f"(*) Robots.txt URL: {robots_url}")
        robots_url_response = self.request.get_data(url=robots_url, timeout=20, retries=self.retry_count, delay=self.__get_delay())
        # print(robots_url_response)
        self.__delay()

        sitemaps = []
        if robots_url_response.status_code == 200:
            for line in robots_url_response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    sitemaps.append(sitemap_url)
        print(f"(*) Discovered sitemap URLs: {sitemaps}")
        self.__delay()

        all_urls = []
        for sitemap_url in sitemaps:
            all_urls.extend(self.__get_urls_from_sitemap(sitemap_url))
        all_prod_urls = list(filter(lambda url: "prd" in url or "mkp" in url, set(all_urls)))
        print(f"(*) Found product URLs: {all_prod_urls}")
        return all_prod_urls
    
    def scrap_data(self) -> None:
        prod_sitemaps = self.__locate_product_sitemaps()


def main():
    ### castorama, leroy_merlin, manomano
    supplier_name = "castorama"
    config_path = f"../configs/{supplier_name}.yaml"
    config = load_yaml_config(path=config_path)
    parsed = urlparse(config["url"])
    config["url"] = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    print(f"(*) Config: {config}")

    scrapper = Scrapper(config=config)
    scrapper.scrap_data()


main()

