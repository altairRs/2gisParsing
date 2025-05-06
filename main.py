from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import pandas as pd

# --- Confirmed Selectors (based on your input) ---
STARTING_URL = "https://2gis.kz/astana/search/Рестораны/rubricId/164"

# Selector for the main container of each restaurant card in the list
RESTAURANT_CARD_SELECTOR = "div._1kf6gff"

# Selectors within each restaurant card (relative to RESTAURANT_CARD_SELECTOR)
NAME_SELECTOR = "span._lvwrwt"
ADDRESS_SELECTOR = "span._1w9o2igt"


# --- End of Confirmed Selectors ---

def scrape_first_page_restaurants_astana():
    options = webdriver.ChromeOptions()
    # Set a common user agent to reduce likelihood of being flagged as a bot
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    # Options to make Selenium less detectable
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument('--headless') # Optional: Run in background without opening a browser window
    options.add_argument('--disable-gpu')  # Recommended for headless
    options.add_argument("--start-maximized")  # Start browser maximized

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # Further attempt to hide Selenium's presence
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    all_restaurants_data = []

    print(f"Navigating to: {STARTING_URL}")
    driver.get(STARTING_URL)

    # Wait for the page to load and potentially for a cookie banner to be handled or disappear
    # Increased sleep time for initial load and any overlays
    print("Waiting for initial page elements to load (e.g., cookie banners, main content)...")
    time.sleep(10)  # Adjust as needed; sometimes longer waits are necessary for overlays

    print(f"\n--- Scraping first page ---")

    try:
        # Wait for restaurant cards to be present
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR))
        )
        print("Restaurant cards detected on the page.")
    except TimeoutException:
        print(f"No restaurant cards found on the first page or timed out. Exiting.")
        driver.quit()
        return all_restaurants_data

    restaurant_cards = driver.find_elements(By.CSS_SELECTOR, RESTAURANT_CARD_SELECTOR)

    if not restaurant_cards:
        print(f"No company cards found on the first page with selector '{RESTAURANT_CARD_SELECTOR}'.")
        driver.quit()
        return all_restaurants_data

    print(f"Found {len(restaurant_cards)} restaurant cards on the first page.")

    for card_index, card in enumerate(restaurant_cards):
        restaurant_data = {}
        print(f"  Processing card {card_index + 1}...")
        try:
            # Name
            try:
                # The name is directly within a span with class _lvwrwt, which is inside an <a> tag.
                # We need to find the name span that is a direct child or specific descendant.
                # It's possible the _lvwrwt span contains other child spans (like the green checkmark)
                # So we might need to be more specific if just .text on _lvwrwt grabs too much.

                name_element_candidate = card.find_element(By.CSS_SELECTOR, NAME_SELECTOR)
                # A common structure is <a ...><span class="_lvwrwt"><span>NAME</span><span class="icon"></span></span></a>
                # We try to get the text of the *first* child span of _lvwrwt if it exists,
                # otherwise, the text of _lvwrwt itself.
                try:
                    actual_name_span = name_element_candidate.find_element(By.XPATH, "./span[1]")  # First child span
                    restaurant_data['name'] = actual_name_span.text.strip()
                except NoSuchElementException:
                    restaurant_data['name'] = name_element_candidate.text.strip()  # Fallback

                if not restaurant_data['name']:  # If the name is still empty, try another common pattern
                    alt_name_element = card.find_element(By.CSS_SELECTOR, "a._1rehek > span._lvwrwt > span:first-child")
                    restaurant_data['name'] = alt_name_element.text.strip()

            except NoSuchElementException:
                restaurant_data['name'] = None
                print(f"    - Name not found for card {card_index + 1} using selector '{NAME_SELECTOR}'")

            # Address
            try:
                # The address is in a span with class _1w9o2igt
                # There might be multiple such spans if the address is broken into parts,
                # or if other info (like "29 филиалов") uses the same class.
                # We'll try to get the one that looks like a main address.

                address_elements = card.find_elements(By.CSS_SELECTOR, ADDRESS_SELECTOR)
                # Filter out elements that look like branch counts
                main_address_parts = []
                for el in address_elements:
                    el_text = el.text.strip()
                    if el_text and "филиал" not in el_text.lower():  # "филиал" is Russian for branch
                        main_address_parts.append(el_text)

                restaurant_data['address'] = " ".join(main_address_parts) if main_address_parts else None

            except NoSuchElementException:
                restaurant_data['address'] = None
                print(f"    - Address not found for card {card_index + 1} using selector '{ADDRESS_SELECTOR}'")

            if restaurant_data.get('name'):  # Only add if we have a name
                print(f"    + Collected: {restaurant_data}")
                all_restaurants_data.append(restaurant_data)
            else:
                print(f"    - Card {card_index + 1} skipped (no name found).")

        except Exception as e:
            print(f"    Error parsing card {card_index + 1}: {e}")
        time.sleep(0.2)  # Small delay between processing cards

    driver.quit()
    print(f"\nFinished scraping. Total items collected: {len(all_restaurants_data)}")
    return all_restaurants_data


if __name__ == "__main__":
    print("Starting 2GIS restaurant scraper for Astana (First Page Only)...")
    print("IMPORTANT: This script is for educational purposes. Please ensure you respect 2GIS's Terms of Service.")
    print(
        "Please ensure the CSS SELECTORS at the top of the script are verified for the current 2GIS website structure.")

    scraped_data = scrape_first_page_restaurants_astana()

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        # Ensure all desired columns are present, adding them with None if missing
        expected_columns = ['name', 'address']  # We are only collecting these for now
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None
        df = df[expected_columns]  # Reorder/select columns

        df.to_csv("2gis_astana_restaurants_first_page.csv", index=False, encoding='utf-8-sig')
        print(f"\nSuccessfully scraped {len(df)} restaurants and saved to 2gis_astana_restaurants_first_page.csv")
    else:
        print("\nNo data was scraped.")