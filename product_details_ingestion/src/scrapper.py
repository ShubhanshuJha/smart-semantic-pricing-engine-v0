import time
import random
from urllib.parse import urlparse, urljoin
from sys import path as sys_path
from os import path as os_path, listdir
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
import re
import hashlib
from datetime import datetime
import json
from pathlib import Path

sys_path.append(os_path.realpath('../../'))
sys_path.append(os_path.realpath('../'))
sys_path.append(os_path.realpath('./'))

from utils.operation_utils import load_yaml_config, write_json_data, write_data
from utils.request_utils import RequestUtils
from contants import *


class Scrapper:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.request = RequestUtils()
        self.retry_count = int(config.get("retry_count", "3"))
        self.min_products = int(config.get("output", {}).get("min_products", "100"))
    
    def __get_delay(self) -> float:
        return random.uniform(self.config["rate_limit_seconds"][0], self.config["rate_limit_seconds"][1])
    
    def __delay(self) -> None:
        time.sleep(self.__get_delay())

    def __get_urls_from_sitemap(self, sitemap_url: str) -> list[str]:
        self.__delay()
        response = self.request.get_data(
            url=sitemap_url,
            timeout=10,
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
                        if loc:
                            child_urls = self.__get_urls_from_sitemap(loc.text) or []
                            urls.extend(child_urls)
                else:
                    url_locs = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                    urls.extend([elem.text for elem in url_locs if elem is not None])
            except ET.ParseError as ex:
                print(f"(*) Failed to parse sitemap {sitemap_url}: {ex}")
        return urls
        
    def __locate_product_sitemaps(self) -> list[str]:
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
        all_prod_urls = list(set(all_urls))
        print(f"(*) Few of the product URLs :{all_prod_urls[:5]}")
        return all_prod_urls
    
    def get_region_from_url(self, base_url: str) -> str:
        netloc = urlparse(base_url).netloc.lower()
        
        if netloc.endswith(".fr"):
            return "France"
        elif netloc.endswith(".be"):
            return "Belgium"
        elif netloc.endswith(".it"):
            return "Italy"
        # extend with more mappings as needed
        return "Unknown"
        
    def is_product_page(self, soup, url) -> bool:
        """
        Heuristics:
        - URL contains '.prd' or '/p/' or '/produit' or '/product'
        - OR page has a main <h1> and a price element
        - OR contains typical 'Ajouter au panier' or 'Ajouter au panier' button text
        """
        if url and re.search(r"\.prd(?:$|[^a-zA-Z0-9])|/p/|/prd|/produit|/product", url, re.IGNORECASE):
            return True

        has_h1 = bool(soup.select_one("h1"))
        has_price = bool(soup.select_one("span.price, .product-price, .lm-product-price, [data-testid='price']"))
        if has_h1 and has_price:
            return True

        # check for add-to-cart button or typical CTA text
        if soup.find(string=re.compile(r"Ajouter au panier|Ajouter au panier", re.IGNORECASE)):
            return True

        return False
    
    def get_prices(self, data):
        pattern = re.compile(r"(\d+[.,]?\d*)\s*€(?:\s*/\s*([A-Za-z0-9²]+))?")
        matches = pattern.findall(data)
        get_unit = lambda x: "/" + x.replace("soit", "").replace("Ajouter", "").replace("2", "\u00b2").replace("3", "\u00b3") if x else ""
        return list(map(lambda x: x[0].strip(",").strip(".") + " €" + get_unit(x=x[1]), matches))

    def parse_product_page(self, url, guess_category=None) -> dict:
        """
        Fetch product URL and return structured dict per spec or None on failure.
        """
        try:
            print(f'Exploring url: {url}')
            resp = self.request.get_data(url=url, delay=self.__get_delay())
            soup = BeautifulSoup(resp.text, "html.parser")

            # Product name extraction (broader selectors)
            product_name = None
            for selector in [
                "h1",
                "[data-testid='product-title']",
                ".product-title",
                ".product-name",
                "div[data-product-name]",
                "title"  # fallback to page title if all else fails
            ]:
                el = soup.select_one(selector)
                if el:
                    product_name = el.get_text(strip=True)
                    break
            if not product_name:
                # Try meta title as last resort
                title_tag = soup.select_one("title")
                if title_tag:
                    product_name = title_tag.get_text(strip=True)

            # Price extraction (broader selectors and regex fallback)
            raw_price = None
            for selector in [
                "span.price",
                ".product-price",
                ".lm-product-price",
                "[data-testid='price']",
                ".price__value",
                ".price",
                "div[data-price]",
                "meta[itemprop='price']",
            ]:
                el = soup.select_one(selector)
                if el:
                    raw_price = el.get_text(strip=True)
                    break
            # Fallback: Try regex search in all text if still missing
            if not raw_price:
                price_matches = self.get_prices(data=soup.get_text())
                if price_matches:
                    raw_price = price_matches
            
            price, price_unit = raw_price[0].split(" ")

            # build stable product_id from URL
            pid_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
            product_id = f"{self.config['supplier']}|{pid_hash}"

            # final object - required fields
            description = None
            region = self.get_region_from_url(self.config[next(filter(lambda x: "url" in x.lower(), self.config))])
            vat_rate = None
            quality_score = None
            VALUES = [product_id, product_name, description, price, price_unit, region, self.config["supplier"].title(),
                      vat_rate, quality_score, url]
            product = dict(zip(PRODUCT_DATA_INGESTION_SCHEMA, VALUES))

            # Basic validation: required fields
            if not product_name or not raw_price or not url:
                # Not a complete product: return empty dict to let caller skip
                return {}
            return product
        except Exception as e:
            print(f"(*) Error in parse_product_page({url}) → {e}")
            return {}
    
    def get_product_data(self, prod_url: str) -> list[dict]:
        seen_urls = set()
        products = []

        print(f"(*) Exploring sitemap: {prod_url}")
        locs = self.__get_urls_from_sitemap(sitemap_url=prod_url)
        print(f"(*) Sitemap {prod_url} contains {len(locs)} loc entries")

        # iterate each loc sequentially (for loop as you requested)
        for loc in locs:
            if loc in seen_urls:
                continue
            seen_urls.add(loc)
            self.__delay()

            # fetch the page
            try:
                resp = self.request.get_data(url=loc, delay = self.__get_delay())
            except Exception as e:
                print(f"(*) Skipping {loc}: fetch failed ({e})")
                continue

            # parse HTML and decide if product page
            try:
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                print(f"(*) Failed parsing HTML for {loc}: {e}")
                continue

            if not self.is_product_page(soup, loc):
                # Not a product detail page — skip to next loc (this respects "return to sitemap and continue")
                continue

            # Parse product detail
            prod = self.parse_product_page(loc, guess_category=None)
            if prod:
                products.append(prod)
                print(f"(*) Collected product: {prod['material_name'][:60]} -> {prod['source']}")
            else:
                print(f"(*) Page looks like product but parsing incomplete for {loc}")

            # stop if we reached required number of products
            if len(products) >= self.min_products:
                break

        # dedupe by product_id
        unique = {}
        for p in products:
            unique[p["product_id"]] = p
        return list(unique.values())

    def scrap_data(self) -> None:
        prod_sitemaps = self.config["sitemap_urls"] if "sitemap_urls" in self.config else self.__locate_product_sitemaps()
        print(f"(*) Total {len(prod_sitemaps)} sitemaps to explore.")
        final_list = []
        for prod_sitemap in prod_sitemaps:
            final_list.extend(self.get_product_data(prod_url=prod_sitemap))
            if len(final_list) >= self.min_products:
                print(f"(*) Product limit {self.min_products} reached... Stopping fetching process...")
                break
        file_name = f"../{self.config['output']['directory']}{self.config['supplier']}_materials.json"
        output_path = write_json_data(data=final_list, path=file_name, mode='a')
        print(f"✅ Ingested data for {len(final_list)} products -> {output_path}")


def main() -> None:
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

