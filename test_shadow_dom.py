from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def test_shadow_dom():
    """Test shadow DOM functionality with a simple page."""
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Create driver
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navigate to a simple test page
        driver.get("https://www.google.com")
        print("Navigated to Google")
        
        # Test the shadow DOM function
        def find_element_in_shadow_dom(host_selector, target_selector):
            """Find an element inside shadow DOM using JavaScript."""
            script = """
            console.log('Searching for shadow DOM element...');
            console.log('Host selector:', arguments[0]);
            console.log('Target selector:', arguments[1]);
            
            const host = document.querySelector(arguments[0]);
            console.log('Host element found:', host);
            
            if (host) {
                console.log('Host has shadowRoot:', !!host.shadowRoot);
                if (host.shadowRoot) {
                    const element = host.shadowRoot.querySelector(arguments[1]);
                    console.log('Element found in shadow DOM:', element);
                    return element;
                }
            }
            console.log('No element found');
            return null;
            """
            result = driver.execute_script(script, host_selector, target_selector)
            print(f"JavaScript result for {host_selector} -> {target_selector}: {result}")
            return result
        
        # Test with a simple div
        print("Testing shadow DOM function...")
        test_result = find_element_in_shadow_dom("*", "div")
        print(f"Test result: {test_result}")
        
        # Check for shadow DOM elements
        shadow_elements_script = """
        const shadowElements = [];
        const allElements = document.querySelectorAll('*');
        
        for (let element of allElements) {
            if (element.shadowRoot) {
                shadowElements.push({
                    tagName: element.tagName,
                    id: element.id,
                    className: element.className,
                    shadowContent: element.shadowRoot.innerHTML.substring(0, 200) + '...'
                });
            }
        }
        
        console.log('Shadow DOM elements found:', shadowElements);
        return shadowElements;
        """
        shadow_elements = driver.execute_script(shadow_elements_script)
        print(f'Shadow DOM elements on page: {shadow_elements}')
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    test_shadow_dom()
