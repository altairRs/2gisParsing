from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, \
    StaleElementReferenceException
import time
import pandas as pd
import re

# --- Selectors ---
STARTING_URL = "https://2gis.kz/astana/search/Рестораны/rubricId/164"
RESTAURANT_CARD_SELECTOR = "div._1kf6gff"
NAME_SELECTOR = "span._lvwrwt"
ADDRESS_SELECTOR = "div._klarpw"
SCROLLABLE_ELEMENT_SELECTOR = "div._1rkbbi0x[data-scroll='true']"

# Pagination Selectors
NEXT_PAGE_BUTTON_ACTIVE_SELECTOR = "div._n5hmn94:nth-child(2)"  # The clickable "Next" arrow's container
# Class that the "Next Page" button's container gets when it's disabled (becomes the right-most greyed out arrow)
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


def scroll_list_fully(driver, list_container_selector):
    print("  Attempting to scroll the list container fully...")
    try:
        list_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, list_container_selector))
        )
        last_scroll_top = -1
        current_scroll_top = driver.execute_script("return arguments[0].scrollTop", list_container)
        scroll_attempts = 0
        while scroll_attempts < 20:
            driver.execute_script("arguments[0].scrollTop += arguments[0].clientHeight;", list_container)
            time.sleep(0.7)
            last_scroll_top = current_scroll_top
            current_scroll_top = driver.execute_script("return arguments[0].scrollTop", list_container)
            print(
                f"    Scrolled list. Old scrollTop: {last_scroll_top}, New scrollTop: {current_scroll_top}, Attempt: {scroll_attempts + 1}")
            if current_scroll_top == last_scroll_top:
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_container)
                time.sleep(1)
                current_scroll_top = driver.execute_script("return arguments[0].scrollTop", list_container)
                if current_scroll_top == last_scroll_top:
                    print("    List scroll position no longer changing. Assuming end of current page's list.")
                    break
            scroll_attempts += 1
        print("  Finished scrolling list attempts for this page.")
    except TimeoutException:
        print(f"  Scrollable list container '{list_container_selector}' not found in time.")
    except Exception as e:
        print(f"  Error during list scrolling: {e}")


def scrape_restaurants_astana_all_pages():
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
    processed_restaurant_links = set()  # To avoid duplicates if an item appears on multiple pages during load

    print(f"Navigating to: {STARTING_URL}")
    driver.get(STARTING_URL)
    print("Waiting 10s for initial page load & potential overlays...")
    time.sleep(5)
    attempt_to_close_cookie_banner(driver)
    time.sleep(5)

    page_num = 1
    while True:
        print(f"\n--- Scraping Page {page_num} ---")

        scroll_list_fully(driver, SCROLLABLE_ELEMENT_SELECTOR)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR))
            )
        except TimeoutException:
            print(f"No restaurant card containers found on page {page_num} after scrolling. Assuming end or error.")
            break

        restaurant_cards = driver.find_elements(By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR)
        if not restaurant_cards:
            print(f"No company cards found on page {page_num} even after scroll. Ending.")
            break

        print(f"Found {len(restaurant_cards)} restaurant card containers on page {page_num}.")

        new_items_on_page = 0
        for card_index, card_container in enumerate(restaurant_cards):
            restaurant_data = {'name': None, 'address': None}  # Initialize with None
            print(f"  Processing card {card_index + 1}/{len(restaurant_cards)}...")

            name_text_raw = None
            address_text_raw = None
            item_link = None

            try:
                # Try to get a unique link for the item to avoid duplicates
                try:
                    link_element = card_container.find_element(By.CSS_SELECTOR, "a._1rehek")  # Common link selector
                    item_link = link_element.get_attribute('href')
                    if item_link in processed_restaurant_links:
                        print(f"    Skipping duplicate item: {item_link}")
                        continue
                except NoSuchElementException:
                    pass  # No unique link found, will rely on name/address combo

                driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});",
                                      card_container)
                time.sleep(0.6)  # Wait for card to settle after scroll

                try:
                    name_element = WebDriverWait(card_container, 7).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, NAME_SELECTOR))
                    )
                    full_name_text = name_element.text.strip()
                    if full_name_text:
                        name_text_raw = full_name_text.split('\n')[0].strip()
                except TimeoutException:
                    print(f"    - Name ('{NAME_SELECTOR}') timed out or not visible for card {card_index + 1}")
                except NoSuchElementException:
                    print(f"    - Name ('{NAME_SELECTOR}') not found for card {card_index + 1}")

                try:
                    address_element = WebDriverWait(card_container, 7).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, ADDRESS_SELECTOR))
                    )
                    address_text_raw = address_element.text.strip()
                except TimeoutException:
                    print(f"    - Address ('{ADDRESS_SELECTOR}') timed out or not visible for card {card_index + 1}")
                except NoSuchElementException:
                    print(f"    - Address ('{ADDRESS_SELECTOR}') not found for card {card_index + 1}")

                restaurant_data['name'] = clean_text(name_text_raw)
                restaurant_data['address'] = clean_text(address_text_raw)

                if restaurant_data.get('name') and restaurant_data.get('address'):
                    print(f"    + Collected: {restaurant_data}")
                    all_restaurants_data.append(restaurant_data)
                    if item_link:
                        processed_restaurant_links.add(item_link)
                    new_items_on_page += 1
                else:
                    print(
                        f"    - Card {card_index + 1} skipped (missing name or address). Raw name: '{name_text_raw}', Raw address: '{address_text_raw}'")

            except StaleElementReferenceException:
                print(f"    StaleElementReferenceException for card {card_index + 1}. Skipping.")
            except Exception as e:
                print(f"    Error parsing card {card_index + 1}: {type(e).__name__} - {e}")

        if new_items_on_page == 0 and page_num > 1:  # If no new items were added on this page (and it's not the first)
            print("No new items found on this page, likely end of unique results.")
            # break # Optional: break if no new items for a while

        # --- Pagination Logic ---
        try:
            print("  Looking for 'Next Page' button...")
            # Check if the "Next Page" button is in its disabled state first
            # The disabled button might have the class _7q94tr and be the last div in its container
            # The active "Next Page" button is NEXT_PAGE_BUTTON_ACTIVE_SELECTOR

            # Find the container for pagination controls
            pagination_controls = driver.find_elements(By.CSS_SELECTOR,
                                                       "div._5ocwns > div")  # _5ocwns is the parent of _7q94tr and _n5hmn94
            if not pagination_controls:
                print("  Pagination controls container not found. Assuming end.")
                break

            last_pagination_control = pagination_controls[-1]  # Get the last element in pagination controls

            if NEXT_PAGE_BUTTON_DISABLED_CLASS_CHECK in last_pagination_control.get_attribute("class"):
                print("  'Next Page' button is in disabled state (has class '_7q94tr'). Reached end of pages.")
                break

            # If not disabled, try to find the active next button
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, NEXT_PAGE_BUTTON_ACTIVE_SELECTOR))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", next_button)
            print(f"  Clicked 'Next Page'. Waiting for page {page_num + 1} to load...")
            page_num += 1
            time.sleep(7)  # Crucial: wait for the next page to load content

        except TimeoutException:
            print("  'Next Page' button not clickable or timed out. Assuming end of results.")
            break
        except NoSuchElementException:
            print("  'Next Page' button (active or disabled check) not found. Assuming end of results.")
            break
        except Exception as e_page:
            print(f"  Error during pagination: {type(e_page).__name__} - {e_page}. Assuming end of results.")
            break

    driver.quit()
    print(f"\nFinished scraping. Total items collected: {len(all_restaurants_data)}")
    return all_restaurants_data


if __name__ == "__main__":
    print("Starting 2GIS restaurant scraper for Astana (All Pages)...")
    scraped_data = scrape_restaurants_astana_all_pages()

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        expected_columns = ['name', 'address']
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None
        df = df[expected_columns]

        df.to_csv("2gis_astana_restaurants_all_pages.csv", index=False, encoding='utf-8-sig')
        print(f"\nSuccessfully scraped {len(df)} restaurants and saved to 2gis_astana_restaurants_all_pages.csv")
    else:
        print("\nNo data was scraped.")