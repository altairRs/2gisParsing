from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, \
    StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import time
import pandas as pd
import re
import os
import urllib.parse  # For URL encoding search terms

# --- Base URL Parts ---
BASE_URL_CITY_SEARCH = "https://2gis.kz/astana/search/"

# --- Selectors (Assumed consistent based on your check) ---
ITEM_CARD_SELECTOR = "div._1kf6gff"
NAME_SELECTOR = "span._lvwrwt"
ADDRESS_SELECTOR = "div._klarpw"
SCROLLABLE_ELEMENT_SELECTOR = "div._1rkbbi0x[data-scroll='true']"
NEXT_PAGE_BUTTON_ACTIVE_SELECTOR = "div._n5hmn94:nth-child(2)"
NEXT_PAGE_BUTTON_DISABLED_CLASS_CHECK = "_7q94tr"


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
        "button._1x5s6kk", "div._n1367pl button", "div[data-qa-id='gdpr-banner-button-agree']"
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
    print("  Attempting to scroll the main page fully...")
    # body_element = driver.find_element(By.TAG_NAME, 'body') # Not always reliable for specific panels
    last_page_height = driver.execute_script(
        "return document.documentElement.scrollHeight")  # Use documentElement for full page

    scroll_attempts = 0
    while scroll_attempts < 15:
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(2)  # Increased wait for dynamic content
        new_page_height = driver.execute_script("return document.documentElement.scrollHeight")
        print(
            f"    Scrolled main page. Old height: {last_page_height}, New height: {new_page_height}, Attempt: {scroll_attempts + 1}")
        if new_page_height == last_page_height:
            no_change_scrolls = 0
            while no_change_scrolls < 2 and new_page_height == last_page_height:
                time.sleep(2)
                driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                new_page_height = driver.execute_script("return document.documentElement.scrollHeight")
                if new_page_height != last_page_height: break
                no_change_scrolls += 1
            if new_page_height == last_page_height:
                print("    Main page scroll height no longer changing.")
                break
        last_page_height = new_page_height
        scroll_attempts += 1
    print("  Finished main page scrolling attempts.")


def scrape_category_data(driver, current_category_name):
    category_data = []
    processed_item_identifiers = set()  # Store unique identifiers (link or name+address)
    page_num = 1

    while True:
        print(f"\n--- Scraping Page {page_num} for category '{current_category_name}' ---")

        # Scroll the specific list container for the items on the current page
        # This is important if the list itself is scrollable within a larger page layout
        try:
            list_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, SCROLLABLE_ELEMENT_SELECTOR))
            )
            last_list_scroll_top = -1
            current_list_scroll_top = driver.execute_script("return arguments[0].scrollTop", list_container)
            list_scroll_attempts = 0
            while list_scroll_attempts < 10:  # Scroll the inner list a few times
                driver.execute_script("arguments[0].scrollTop += arguments[0].clientHeight;", list_container)
                time.sleep(0.7)
                last_list_scroll_top = current_list_scroll_top
                current_list_scroll_top = driver.execute_script("return arguments[0].scrollTop", list_container)
                if current_list_scroll_top == last_list_scroll_top:
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight",
                                          list_container)  # One final scroll to bottom
                    time.sleep(0.5)
                    break
                list_scroll_attempts += 1
            print(f"  Finished scrolling list panel for page {page_num}.")
        except TimeoutException:
            print(f"  Scrollable list container '{SCROLLABLE_ELEMENT_SELECTOR}' not found on page {page_num}.")
        except Exception as e_scroll_list:
            print(f"  Error scrolling list panel: {e_scroll_list}")

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ITEM_CARD_SELECTOR))
            )
        except TimeoutException:
            print(f"No item card containers found on page {page_num}. Assuming end for this category.")
            break

        item_cards = driver.find_elements(By.CSS_SELECTOR, ITEM_CARD_SELECTOR)
        if not item_cards:
            print(f"No item cards found on page {page_num}. Ending for this category.")
            break

        print(f"Found {len(item_cards)} item card containers on page {page_num}.")

        new_items_this_page = 0
        for card_index, card_container in enumerate(item_cards):
            data_item = {'name': None, 'address': None, 'category': current_category_name}

            name_text_raw = None
            address_text_raw = None
            item_identifier = None  # Will be link or name+address

            try:
                # Try to get a unique link for the item to avoid duplicates
                try:
                    link_element = card_container.find_element(By.CSS_SELECTOR, "a._1rehek")
                    item_identifier = link_element.get_attribute('href')
                except NoSuchElementException:
                    pass

                    # Scroll the current card container into view
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});",
                                      card_container)
                time.sleep(0.7)

                try:
                    name_element = WebDriverWait(card_container, 7).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, NAME_SELECTOR))
                    )
                    full_name_text = name_element.text.strip()
                    if full_name_text:
                        name_text_raw = full_name_text.split('\n')[0].strip()
                except Exception as e_name:
                    print(f"    - Error/Timeout getting name for card {card_index + 1}: {type(e_name).__name__}")

                try:
                    address_element = WebDriverWait(card_container, 7).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, ADDRESS_SELECTOR))
                    )
                    address_text_raw = address_element.text.strip()
                except Exception as e_addr:
                    print(f"    - Error/Timeout getting address for card {card_index + 1}: {type(e_addr).__name__}")

                data_item['name'] = clean_text(name_text_raw)
                data_item['address'] = clean_text(address_text_raw)

                # Use name+address as identifier if link wasn't found for de-duplication
                if not item_identifier and data_item.get('name') and data_item.get('address'):
                    item_identifier = (data_item['name'], data_item['address'])

                if item_identifier and item_identifier in processed_item_identifiers:
                    print(f"    Skipping duplicate item: {item_identifier}")
                    continue

                if data_item.get('name') and data_item.get('address'):
                    print(f"    + Collected: {data_item}")
                    category_data.append(data_item)
                    if item_identifier:
                        processed_item_identifiers.add(item_identifier)
                    new_items_this_page += 1
                else:
                    print(
                        f"    - Card {card_index + 1} skipped (missing name or address). Raw name: '{name_text_raw}', Raw address: '{address_text_raw}'")

            except StaleElementReferenceException:
                print(f"    StaleElementReferenceException for card {card_index + 1}. Skipping.")
            except Exception as e:
                print(f"    Error parsing card {card_index + 1}: {type(e).__name__} - {e}")

        if page_num > 1 and new_items_this_page == 0:
            print("No new unique items found on this page, likely end of results for this category.")
            break

        # --- Pagination Logic ---
        try:
            print("  Looking for 'Next Page' button...")
            pagination_controls_container = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div._5ocwns"))
            )
            pagination_elements = pagination_controls_container.find_elements(By.CSS_SELECTOR, "div")

            if not pagination_elements or len(pagination_elements) < 2:  # Need at least previous and next/disabled next
                print("  Not enough pagination elements found. Assuming single page or end.")
                break

            last_pagination_element = pagination_elements[-1]

            if NEXT_PAGE_BUTTON_DISABLED_CLASS_CHECK in last_pagination_element.get_attribute("class"):
                print("  'Next Page' button is in disabled state. Reached end of pages for this category.")
                break

            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, NEXT_PAGE_BUTTON_ACTIVE_SELECTOR))
            )
            # Scroll to the pagination controls to make sure button is clickable
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", pagination_controls_container)
            time.sleep(1)

            # Attempt JS click, then regular click if it fails
            try:
                driver.execute_script("arguments[0].click();", next_button)
            except Exception as e_js_click:
                print(f"    JS click failed for next button: {e_js_click}, trying regular click.")
                next_button.click()

            print(f"  Clicked 'Next Page'. Waiting for page {page_num + 1} to load...")
            page_num += 1
            time.sleep(8)

        except TimeoutException:
            print("  'Next Page' button not clickable or timed out. Assuming end of results for category.")
            break
        except NoSuchElementException:
            print("  'Next Page' button structure not found. Assuming end of results for category.")
            break
        except Exception as e_page:
            print(f"  Error during pagination: {type(e_page).__name__} - {e_page}. Assuming end of results.")
            break

    return category_data


def main():
    categories_to_scrape = {
        "Рестораны": "restaurants",
        "Красота": "beauty",
        "Пожить": "accommodations",  # "Пожить" might bring up hotels, hostels, etc.
        "Продукты": "groceries"
    }

    options = webdriver.ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument('--headless')
    options.add_argument('--no-sandbox')  # Often needed for headless in Linux environments
    options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
    options.add_argument('--disable-gpu')
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    output_dir = "scraped_data_2gis_astana"
    os.makedirs(output_dir, exist_ok=True)
    master_data_all_categories = []

    try:
        for search_term_cyrillic, filename_suffix in categories_to_scrape.items():
            print(f"\n\n{'=' * 20} STARTING CATEGORY: {search_term_cyrillic} {'=' * 20}")

            # URL encode the search term
            encoded_search_term = urllib.parse.quote(search_term_cyrillic)
            category_url = f"{BASE_URL_CITY_SEARCH}{encoded_search_term}"
            # If you find specific rubric IDs are better, you'd construct the URL like:
            # category_url = f"{BASE_URL_CITY_SEARCH}{encoded_search_term}/rubricId/YOUR_ID"

            print(f"Navigating to: {category_url}")
            driver.get(category_url)
            print("Waiting 10s for initial page load & potential overlays...")
            time.sleep(5)
            attempt_to_close_cookie_banner(driver)
            time.sleep(5)

            scroll_page_fully(driver)  # Scroll the main page once for the category

            category_specific_data = scrape_category_data(driver, search_term_cyrillic)

            if category_specific_data:
                master_data_all_categories.extend(category_specific_data)
                df_category = pd.DataFrame(category_specific_data)

                expected_columns = ['name', 'address', 'category']
                for col in expected_columns:
                    if col not in df_category.columns:
                        df_category[col] = None
                df_category = df_category[expected_columns]

                file_path = os.path.join(output_dir, f"2gis_astana_{filename_suffix}.csv")
                df_category.to_csv(file_path, index=False, encoding='utf-8-sig')
                print(
                    f"\nSuccessfully scraped {len(df_category)} items for '{search_term_cyrillic}' and saved to {file_path}")
            else:
                print(f"\nNo data scraped for category '{search_term_cyrillic}'.")

            print(f"{'=' * 20} FINISHED CATEGORY: {search_term_cyrillic} {'=' * 20}")
            time.sleep(10)  # Longer pause between categories to be polite

    except Exception as e:
        print(f"An overall error occurred: {e}")
    finally:
        print("Quitting driver...")
        driver.quit()

    if master_data_all_categories:
        df_all = pd.DataFrame(master_data_all_categories)
        expected_columns = ['name', 'address', 'category']
        for col in expected_columns:
            if col not in df_all.columns:
                df_all[col] = None
        df_all = df_all[expected_columns]

        master_file_path = os.path.join(output_dir, "2gis_astana_all_categories_combined.csv")
        df_all.to_csv(master_file_path, index=False, encoding='utf-8-sig')
        print(f"\n\nSuccessfully scraped a total of {len(df_all)} items across all categories.")
        print(f"Combined data saved to {master_file_path}")
    else:
        print("\n\nNo data was scraped from any category.")


if __name__ == "__main__":
    print("Starting 2GIS multi-category scraper for Astana...")
    main()