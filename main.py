from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, \
    NoSuchElementException
import time
import pandas as pd
import os
import urllib.parse

BASE_URL_CITY_SEARCH = "https://2gis.kz/astana/search/"
ITEM_CARD_SELECTOR = "div._1kf6gff"
NAME_SELECTOR = "span._lvwrwt"
ADDRESS_SELECTOR = "div._klarpw"
NEXT_PAGE_BUTTON_ACTIVE_SELECTOR = "div._n5hmn94:nth-child(2)"
NEXT_PAGE_BUTTON_DISABLED_CLASS_CHECK = "_7q94tr"

def scroll_page_fully(driver, max_scrolls=10):
    print("  Scrolling main page...")
    last_height = driver.execute_script("return document.documentElement.scrollHeight")
    for i in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(1.0)
        new_height = driver.execute_script("return document.documentElement.scrollHeight")
        if new_height == last_height and i > 2:
            break
        last_height = new_height
    print("  Finished main page scrolling.")


def scrape_category_data(driver, current_category_name):
    category_data = []
    page_num = 1

    while True:
        print(f"\n--- Scraping Page {page_num} for '{current_category_name}' ---")

        if page_num > 1:
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            time.sleep(1)

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ITEM_CARD_SELECTOR)))
        except TimeoutException:
            print(f"No item cards on page {page_num}. Ending category.")
            break

        item_cards = driver.find_elements(By.CSS_SELECTOR, ITEM_CARD_SELECTOR)
        if not item_cards: break
        print(f"Found {len(item_cards)} item cards.")

        for card_container in item_cards:
            name, address = None, None
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_container)
                time.sleep(0.3)

                name_element = card_container.find_element(By.CSS_SELECTOR, NAME_SELECTOR)
                name = name_element.text.strip().split('\n')[0].strip()

                address_element = card_container.find_element(By.CSS_SELECTOR, ADDRESS_SELECTOR)
                address = address_element.text.strip()

                if name and address:
                    category_data.append({'name': name, 'address': address, 'category': current_category_name})
                    print(f"    + {name} | {address}")

            except NoSuchElementException:
                print(f"    - Name or address element not found in a card. Skipping card.")
            except Exception as e:
                print(f"    - Error processing a card: {type(e).__name__}")

        try:
            pagination_controls_container = driver.find_element(By.CSS_SELECTOR, "div._5ocwns")
            pagination_elements = pagination_controls_container.find_elements(By.CSS_SELECTOR, "div")
            if not pagination_elements or len(pagination_elements) < 2: break
            if NEXT_PAGE_BUTTON_DISABLED_CLASS_CHECK in pagination_elements[-1].get_attribute("class"):
                print("  Next Page button disabled. Reached end.")
                break

            next_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, NEXT_PAGE_BUTTON_ACTIVE_SELECTOR)))
            driver.execute_script("arguments[0].scrollIntoView(true);",
                                  pagination_controls_container)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", next_button)
            page_num += 1
            time.sleep(5)
        except Exception:
            print(f"  Pagination error or end of pages. Ending category.")
            break
    return category_data


def main():
    categories_to_scrape = {
        "Рестораны": "restaurants",
        "Красота": "beauty",
        "Пожить": "accommodations",
        "Продукты": "groceries"
    }

    options = webdriver.ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    output_dir = "scraped_data_2gis_astana_minimal"
    os.makedirs(output_dir, exist_ok=True)
    master_data_all_categories = []

    try:
        for search_term_cyrillic, filename_suffix in categories_to_scrape.items():
            print(f"\n{'=' * 10} CATEGORY: {search_term_cyrillic} {'=' * 10}")
            encoded_search_term = urllib.parse.quote(search_term_cyrillic)
            category_url = f"{BASE_URL_CITY_SEARCH}{encoded_search_term}"

            driver.get(category_url)
            print("Waiting 5s for page load...")
            time.sleep(5)

            scroll_page_fully(driver)
            category_specific_data = scrape_category_data(driver, search_term_cyrillic)

            if category_specific_data:
                master_data_all_categories.extend(category_specific_data)
                df_category = pd.DataFrame(category_specific_data)
                df_category = df_category[['name', 'address', 'category']].fillna('')
                file_path = os.path.join(output_dir, f"2gis_astana_{filename_suffix}.csv")
                df_category.to_csv(file_path, index=False, encoding='utf-8-sig')
                print(f"Saved {len(df_category)} items for '{search_term_cyrillic}' to {file_path}")
            else:
                print(f"No data scraped for '{search_term_cyrillic}'.")
            time.sleep(5)
    finally:
        print("Quitting driver...")
        driver.quit()

    if master_data_all_categories:
        df_all = pd.DataFrame(master_data_all_categories)
        df_all = df_all[['name', 'address', 'category']].fillna('')
        master_file_path = os.path.join(output_dir, "2gis_astana_all_categories_combined_minimal.csv")
        df_all.to_csv(master_file_path, index=False, encoding='utf-8-sig')
        print(f"\nTotal {len(df_all)} items saved to {master_file_path}")
    else:
        print("\nNo data scraped from any category.")


if __name__ == "__main__":
    print("Starting scraper...")
    main()