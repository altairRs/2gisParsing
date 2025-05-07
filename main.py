from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, \
    StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import time
import pandas as pd
import re

# --- Selectors ---
STARTING_URL = "https://2gis.kz/astana/search/Рестораны/rubricId/164"
RESTAURANT_CARD_SELECTOR = "div._1kf6gff"
NAME_SELECTOR = "span._lvwrwt"
ADDRESS_SELECTOR = "div._klarpw"

SCROLLABLE_ELEMENT_SELECTOR = "div._1rkbbi0x[data-scroll='true']"


# --- End of Selectors ---


def clean_text(text):
    if text is None:
        return None
    text = text.replace("Реклама", "")
    text = re.sub(r'\*?Подробности по т\. .*$', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'Есть противопоказания.*$', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\d+\s+филиал(ов|а)?', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\s+', ' ', text).strip()
    return text if text else None


def attempt_to_close_cookie_banner(driver):
    cookie_banner_selectors = [
        "button._1x5s6kk",
        "div._n1367pl button",
        "div[data-qa-id='gdpr-banner-button-agree']"
    ]
    for i, selector in enumerate(cookie_banner_selectors):
        try:
            print(f"  Trying to find cookie banner/overlay button with selector: {selector}")
            cookie_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            print("  Cookie banner/overlay button found. Attempting to click.")
            driver.execute_script("arguments[0].click();", cookie_button)
            print("  Clicked cookie banner/overlay button.")
            time.sleep(2)
            return True
        except TimeoutException:
            print(f"  Cookie banner/overlay (attempt {i + 1}) not found or not clickable with selector: {selector}")
        except Exception as e:
            print(f"  Error interacting with cookie banner/overlay (attempt {i + 1}): {e}")
    return False


def scroll_page_fully(driver):
    print("  Attempting to scroll the main page fully to ensure all elements are potentially triggered...")
    body_element = driver.find_element(By.TAG_NAME, 'body')
    last_page_height = driver.execute_script("return document.body.scrollHeight")

    scroll_attempts = 0
    while scroll_attempts < 15:  # Limit attempts to prevent infinite loops
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)  # Wait for content to load
        new_page_height = driver.execute_script("return document.body.scrollHeight")
        print(
            f"    Scrolled main page. Old height: {last_page_height}, New height: {new_page_height}, Attempt: {scroll_attempts + 1}")
        if new_page_height == last_page_height:
            # Try a few more times just in case
            no_change_scrolls = 0
            while no_change_scrolls < 2 and new_page_height == last_page_height:
                time.sleep(1.5)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                new_page_height = driver.execute_script("return document.body.scrollHeight")
                if new_page_height != last_page_height: break
                no_change_scrolls += 1
            if new_page_height == last_page_height:
                print("    Main page scroll height no longer changing.")
                break
        last_page_height = new_page_height
        scroll_attempts += 1
    print("  Finished main page scrolling attempts.")


def scrape_restaurants_astana():
    options = webdriver.ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")
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
    print("Waiting 10s for initial page load & potential overlays...")
    time.sleep(5)
    attempt_to_close_cookie_banner(driver)
    time.sleep(5)

    # --- SCROLL THE ENTIRE PAGE FIRST ---
    scroll_page_fully(driver)
    # --- THEN GET ALL CARD CONTAINERS ---

    print(f"\n--- Finding restaurant card containers after scrolling ---")

    try:
        # Wait for at least one card to be present
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR))
        )
        print("At least one restaurant card container detected.")
    except TimeoutException:
        print(f"No restaurant card containers found after scrolling. Exiting.")
        driver.quit()
        return all_restaurants_data

    restaurant_cards = driver.find_elements(By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR)

    if not restaurant_cards:
        print(f"No company cards found with selector '{RESTAURANT_CARD_SELECTOR}' after scrolling.")
        driver.quit()
        return all_restaurants_data

    print(f"Found {len(restaurant_cards)} restaurant card containers.")

    for card_index, card_container in enumerate(restaurant_cards):
        restaurant_data = {}
        print(f"  Processing card {card_index + 1}/{len(restaurant_cards)}...")

        name_text_raw = None
        address_text_raw = None

        try:
            # Scroll the current card container into view (center)
            # This is important for elements that might lazy-load their content
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", card_container)
            time.sleep(0.7)  # Increased wait after scrolling card into view

            # Name
            try:
                # Wait for the name element to be VISIBLE within this specific card
                name_element = WebDriverWait(card_container, 7).until(  # Increased wait to 7s
                    EC.visibility_of_element_located((By.CSS_SELECTOR, NAME_SELECTOR))
                )
                full_name_text = name_element.text.strip()
                if full_name_text:
                    name_text_raw = full_name_text.split('\n')[0].strip()
            except TimeoutException:
                print(f"    - Name ('{NAME_SELECTOR}') timed out or not visible for card {card_index + 1}")
            except NoSuchElementException:
                print(f"    - Name ('{NAME_SELECTOR}') not found for card {card_index + 1}")

            # Address
            try:
                # Wait for the address block to be VISIBLE within this specific card
                address_element = WebDriverWait(card_container, 7).until(  # Increased wait to 7s
                    EC.visibility_of_element_located((By.CSS_SELECTOR, ADDRESS_SELECTOR))
                )
                address_text_raw = address_element.text.strip()
            except TimeoutException:
                print(f"    - Address ('{ADDRESS_SELECTOR}') timed out or not visible for card {card_index + 1}")
            except NoSuchElementException:
                print(f"    - Address ('{ADDRESS_SELECTOR}') not found for card {card_index + 1}")

            restaurant_data['name'] = clean_text(name_text_raw)
            restaurant_data['address'] = clean_text(address_text_raw)

            if restaurant_data.get('name') and restaurant_data.get('address'):  # Require both for a "good" entry
                print(f"    + Collected: {restaurant_data}")
                all_restaurants_data.append(restaurant_data)
            else:
                print(
                    f"    - Card {card_index + 1} skipped (missing name or address). Raw name: '{name_text_raw}', Raw address: '{address_text_raw}'")

        except StaleElementReferenceException:
            print(f"    StaleElementReferenceException for card {card_index + 1}. Skipping this card.")
        except Exception as e:
            print(f"    Error parsing card {card_index + 1}: {type(e).__name__} - {e}")

    driver.quit()
    print(f"\nFinished scraping. Total items collected: {len(all_restaurants_data)}")
    return all_restaurants_data


if __name__ == "__main__":
    print("Starting 2GIS restaurant scraper for Astana (Attempting to scroll and get all on first page load)...")
    scraped_data = scrape_restaurants_astana()

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        expected_columns = ['name', 'address']
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None
        df = df[expected_columns]

        df.to_csv("2gis_astana_restaurants_scrolled.csv", index=False, encoding='utf-8-sig')
        print(f"\nSuccessfully scraped {len(df)} restaurants and saved to 2gis_astana_restaurants_scrolled.csv")
    else:
        print("\nNo data was scraped.")