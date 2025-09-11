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

from utils.operation_utils import load_yaml_config, write_json_data
from utils.request_utils import RequestUtils


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
    
    def normalize_price(self, price_str) -> dict:
        """
        Normalize French price text to {amount, currency, price_type}.
        Handles: "29,90 €", "2,50 €/m²", "149 € / pack", "1 234,56 €"
        """
        if not price_str or not isinstance(price_str, str):
            return {}
        s = price_str.strip().replace("\xa0", " ").replace("\u202f", " ")
        # extract first numeric token
        m = re.search(r"([0-9\.\s,]+)", s)
        if not m:
            return {}
        token = m.group(1)
        # remove spaces and dots used as thousand separators, convert comma to dot
        token = token.replace(" ", "").replace("\u00A0", "")
        # If token contains both '.' and ',' assume '.' thousands, ',' decimals => remove '.' then replace ','
        if "." in token and "," in token:
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", ".")
        try:
            amount = float(token)
        except Exception:
            return {}
        currency = "EUR" if "€" in s else None
        if "m²" in s or "/m" in s:
            price_type = "per_m2"
        elif "pack" in s or "/pack" in s:
            price_type = "pack"
        else:
            price_type = "unit"
        return {"amount": round(amount, 2), "currency": currency, "price_type": price_type}

    def extract_measurement(self, text) -> dict:
        if not text:
            return {}
        # look for unit patterns and a preceding number
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(m²|m2|cm|mm|kg|g|l|ml|litre|litres|pack|unité|unites|unités)", text, re.IGNORECASE)
        if m:
            qty = m.group(1).replace(",", ".")
            unit = m.group(2)
            try:
                qty_num = float(qty)
            except Exception:
                qty_num = None
            return {"quantity": qty_num, "unit": unit.lower()}
        return {}

    def parse_product_page(self, url, guess_category=None) -> dict:
        """
        Fetch product URL and return structured dict per spec or None on failure.
        """
        try:
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
                price_matches = re.findall(r"(\d+[.,]\d+)\s*€", soup.get_text())
                if price_matches:
                    raw_price = price_matches[0] + " €"

            price = self.normalize_price(raw_price)


            # brand
            brand_el = soup.select_one("span[itemprop='brand'], .brand, [data-testid='brand'], .product-brand")
            brand = brand_el.get_text(strip=True) if brand_el else None

            # breadcrumbs -> category inference
            crumbs = []
            # try a variety of breadcrumb selectors
            for sel in ("nav.breadcrumb li a", ".breadcrumb li a", ".breadcrumb a", ".breadcrumbs a"):
                els = soup.select(sel)
                if els:
                    crumbs = [e.get_text(strip=True) for e in els if e.get_text(strip=True)]
                    break
            category = guess_category or (" > ".join(crumbs) if crumbs else None)

            # measurement search in product name + description
            desc_text = ""
            desc_blocks = soup.select(".product-description, .pdp-description, #description, .description")
            if desc_blocks:
                desc_text = " ".join(b.get_text(" ", strip=True) for b in desc_blocks)
            search_text = " ".join([t for t in (product_name or "", desc_text) if t])
            measurement = self.extract_measurement(search_text)

            # availability: look for text or existence of 'add to cart' CTA
            availability = "unknown"
            if soup.find(string=re.compile(r"en stock|disponible", re.IGNORECASE)):
                availability = "in_stock"
            elif soup.find(string=re.compile(r"rupture|indisponible|épuisé", re.IGNORECASE)):
                availability = "out_of_stock"
            elif soup.find(string=re.compile(r"précommande|preorder", re.IGNORECASE)):
                availability = "preorder"

            # image: prefer og:image, else first product image tag
            img_meta = soup.select_one("meta[property='og:image'], meta[name='og:image']")
            if img_meta and img_meta.has_attr("content"):
                image_url = img_meta["content"]
            else:
                img_tag = soup.select_one(".product-media img, .product-image img, img")
                image_url = img_tag.get("src") if img_tag and img_tag.has_attr("src") else None

            # build stable product_id from URL
            pid_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
            product_id = f"{self.config['supplier']}|{pid_hash}"

            # final object - required fields
            product = {
                "product_id": product_id,
                "supplier": self.config["supplier"],
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "category": category,
                "product_name": product_name,
                "brand": brand,
                "price": price,
                "measurement": measurement,
                "availability": availability,
                "url": url,
                "image_url": image_url,
                "variations": [],  # left empty; could be populated by further parsing
                "source": url,
                "raw": {"price_str": raw_price},
            }

            # Basic validation: required fields
            if not product_name or not price or not url:
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
                print(f"(*) Collected product: {prod['product_name'][:60]} -> {prod['url']}")
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
        output_path = write_json_data(data=final_list, path=file_name)
        print(f"✅ Scraped {len(final_list)} products -> {output_path}")


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

