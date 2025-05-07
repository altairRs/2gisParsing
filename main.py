from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import pandas as pd
import re

# --- Selectors You've Helped Confirm/Identify ---
STARTING_URL = "https://2gis.kz/astana/search/Рестораны/rubricId/164"
RESTAURANT_CARD_SELECTOR = "div._1kf6gff"  # Main container for each restaurant
NAME_SELECTOR = "span._lvwrwt"  # The span directly containing or wrapping the name
ADDRESS_SELECTOR = "div._klarpw"  # The div containing all address parts


# --- End of Selectors ---

def clean_text(text):
    """Helper to remove known ad/extra texts and excessive whitespace."""
    if text is None:
        return None

    # Remove "Реклама" and typical disclaimer patterns
    text = text.replace("Реклама", "")
    text = re.sub(r'\*?Подробности по т\. .*$', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'Есть противопоказания.*$', '', text, flags=re.IGNORECASE).strip()  # Another common ad disclaimer

    # Remove typical "N филиалов" text if it's part of the address block
    text = re.sub(r'\d+\s+филиал(ов|а)?', '', text, flags=re.IGNORECASE).strip()

    # Replace multiple spaces/newlines with a single space and strip
    text = re.sub(r'\s+', ' ', text).strip()
    return text if text else None


def scrape_first_page_restaurants_astana():
    options = webdriver.ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    all_restaurants_data = []

    print(f"Navigating to: {STARTING_URL}")
    driver.get(STARTING_URL)
    print("Waiting for initial page elements to load...")
    time.sleep(10)

    print(f"\n--- Scraping first page ---")

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR))
        )
        print("Restaurant cards detected.")
    except TimeoutException:
        print(f"No restaurant cards found or timed out. Exiting.")
        driver.quit()
        return all_restaurants_data

    restaurant_cards = driver.find_elements(By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR)

    if not restaurant_cards:
        print(f"No company cards found with selector '{RESTAURANT_CARD_SELECTOR}'.")
        driver.quit()
        return all_restaurants_data

    print(f"Found {len(restaurant_cards)} restaurant cards.")

    for card_index, card in enumerate(restaurant_cards):
        restaurant_data = {}
        print(f"  Processing card {card_index + 1}...")

        name_text_raw = None
        address_text_raw = None

        try:
            # Name
            try:
                name_element = card.find_element(By.CSS_SELECTOR, NAME_SELECTOR)
                # Get all text within the name container. The actual name is usually the most prominent.
                # We take the first line of the .text attribute, which often works.
                full_name_text = name_element.text.strip()
                if full_name_text:
                    name_text_raw = full_name_text.split('\n')[0].strip()
            except NoSuchElementException:
                print(f"    - Name element ('{NAME_SELECTOR}') not found for card {card_index + 1}")

            # Address
            try:
                address_element = card.find_element(By.CSS_SELECTOR, ADDRESS_SELECTOR)
                # Get all text within the address container.
                address_text_raw = address_element.text.strip()
            except NoSuchElementException:
                print(f"    - Address element ('{ADDRESS_SELECTOR}') not found for card {card_index + 1}")

            restaurant_data['name'] = clean_text(name_text_raw)
            restaurant_data['address'] = clean_text(address_text_raw)

            if restaurant_data.get('name'):  # Only add if we have a name after cleaning
                print(f"    + Collected: {restaurant_data}")
                all_restaurants_data.append(restaurant_data)
            else:
                print(
                    f"    - Card {card_index + 1} skipped (no name found after cleaning and attempting extraction). Raw name was: '{name_text_raw}'")

        except Exception as e:
            print(f"    Error parsing card {card_index + 1}: {e}")
        time.sleep(0.1)

    driver.quit()
    print(f"\nFinished scraping. Total items collected: {len(all_restaurants_data)}")
    return all_restaurants_data


if __name__ == "__main__":
    print("Starting 2GIS restaurant scraper for Astana (First Page Only)...")
    scraped_data = scrape_first_page_restaurants_astana()

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        expected_columns = ['name', 'address']
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None
        df = df[expected_columns]

        df.to_csv("2gis_astana_restaurants_first_page.csv", index=False, encoding='utf-8-sig')
        print(f"\nSuccessfully scraped {len(df)} restaurants and saved to 2gis_astana_restaurants_first_page.csv")
    else:
        print("\nNo data was scraped.")