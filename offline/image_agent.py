"""
Image Agent: Handles image fetching and processing using Unsplash API and GPT.
"""
import os
from unsplash.api import Api
from unsplash.auth import Auth
import openai
from dotenv import load_dotenv

load_dotenv()

# --- Unsplash API Configuration ---
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
UNSPLASH_SECRET_KEY = os.getenv("UNSPLASH_SECRET_KEY")
# Note: For public actions, redirect_uri and code are not strictly needed for client-side search
# but the library might require them for full auth flow, which we are not using here.
# We are primarily using the Access Key for searching.
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob" # Placeholder if needed
CODE = "" # Placeholder if needed

unsplash_api = None
if UNSPLASH_ACCESS_KEY:
    try:
        # Simplify Auth initialization for public access using only client_id (Access Key)
        auth = Auth(client_id=UNSPLASH_ACCESS_KEY, client_secret=UNSPLASH_SECRET_KEY, redirect_uri=REDIRECT_URI) # Keep secret & URI for now
        unsplash_api = Api(auth)
        print("Unsplash API client initialized.") # No change to print message yet
    except Exception as e:
        print(f"Error initializing Unsplash API: {e}")
        unsplash_api = None
else:
    print("UNSPLASH_ACCESS_KEY not found in environment variables. Unsplash API client not initialized.")

# --- OpenAI Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    print("OpenAI API key configured.")
else:
    print("OPENAI_API_KEY not found. OpenAI functions will not work.")

def generate_image_keywords(style_description: str, image_context: str, image_type: str = "photo") -> str:
    """
    Generates search keywords for Unsplash using GPT-3.5 Turbo.

    Args:
        style_description: Overall style (e.g., "modern minimalist kitchen", "vibrant fitness gym").
        image_context: Specific context (e.g., "hero background", "about us section image", "product display").
        image_type: Type of image, e.g., 'photo', 'illustration'.

    Returns:
        A string of comma-separated keywords.
    """
    if not openai.api_key:
        print("OpenAI API key not configured. Cannot generate keywords.")
        # Fallback keywords
        return f"{style_description}, {image_context}, {image_type}"

    prompt = (
        f"Generate 3-5 concise and effective Unsplash search keywords for a {image_type}. "
        f"The overall theme/style is '{style_description}'. "
        f"donot use the color for the keywords just from style , just take the main core like what is the business about or what is the image about. "
        f"The specific placement or purpose of the image is '{image_context}'. "
        f"Focus on nouns, adjectives, and concepts relevant to visual search. "
        f"Avoid long phrases. Return keywords as a comma-separated list. "
        f"Example: Style 'luxury spa', Context 'hero background' -> 'luxury, spa, serene, relaxation, wellness, background'"
    )

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at generating concise image search keywords for stock photo websites like Unsplash."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.5
        )
        keywords = response.choices[0].message.content
        print(f"Generated keywords for '{style_description} - {image_context}': {keywords}")
        return keywords
    except Exception as e:
        print(f"Error generating image keywords with OpenAI: {e}")
        # Fallback keywords in case of API error
        return f"{style_description}, {image_context}, {image_type}, high quality"

def find_image_on_unsplash(keywords: str) -> str | None:
    """
    Searches Unsplash for an image based on keywords.

    Args:
        keywords: Comma-separated keywords.

    Returns:
        The URL of the 'regular' size image if found, otherwise None.
    """
    if not unsplash_api:
        print("Unsplash API client not initialized. Cannot search for images.")
        return None

    try:
        print(f"Searching Unsplash for: '{keywords}'")
        # Remove orientation parameter which is causing the TypeError
        photos = unsplash_api.search.photos(query=keywords, per_page=5)
        
        if photos and photos['results']:
            # Select the first image for simplicity
            selected_image = photos['results'][0]
            image_url = selected_image.urls.regular
            print(f"Found image on Unsplash: {image_url} (ID: {selected_image.id})")
            return image_url
        else:
            print(f"No images found on Unsplash for keywords: {keywords}")
            return None
    except Exception as e:
        print(f"Error searching Unsplash: {e}")
        return None

# --- Placeholder for integration logic ---
def get_image_for_element(style_description: str, element_context: str, element_type: str = "image_widget", current_image_url: str | None = None) -> str | None:
    """
    Main function to be called by the theme processing logic.
    Generates keywords, finds an image, and returns its URL.

    Args:
        style_description: The overall theme style.
        element_context: Context of the image (e.g., 'hero', 'about_us_image', 'contact_form_background').
        element_type: Type of element (e.g., 'image_widget', 'background_image', 'gallery_item').
        current_image_url: The existing image URL (can be used for context or to avoid re-fetching if not needed).

    Returns:
        A new image URL, or None if an error occurs or no image is found.
    """
    # For now, we always try to get a new image. 
    # Future enhancements could involve checking if current_image_url is already suitable or a placeholder.
    
    keywords = generate_image_keywords(style_description, element_context, image_type="photo")
    
    # Note: We're keeping this orientation logic for future use, but not using it in the search for now
    # since the python-unsplash library doesn't support the orientation parameter directly.
    orientation = "landscape" # Default
    if "hero" in element_context.lower() or "background" in element_context.lower():
        orientation = "landscape"
    elif "portrait" in element_context.lower() or "profile" in element_context.lower():
        orientation = "portrait"
    
    # Call find_image_on_unsplash without the orientation parameter
    new_image_url = find_image_on_unsplash(keywords)
    
    if new_image_url:
        print(f"Selected image for '{element_context}' with style '{style_description}': {new_image_url}")
        return new_image_url
    else:
        print(f"Could not find a suitable image for '{element_context}' with style '{style_description}'.")
        return None

if __name__ == '__main__':
    # Test the functions (ensure .env is set up with your keys)
    print("Testing Image Agent functions...")
    
    # Test OpenAI Keyword Generation
    test_style = "modern tech startup"
    test_context_hero = "website hero section background"
    test_context_about = "about us page team photo"
    
    hero_keywords = generate_image_keywords(test_style, test_context_hero)
    # Expected: keywords related to modern tech, startup, hero, background
    
    about_keywords = generate_image_keywords(test_style, test_context_about, image_type="group photo")
    # Expected: keywords related to modern tech, team, collaboration, office

    # Test Unsplash Image Search (using a generic keyword to increase chances of finding something)
    if hero_keywords and unsplash_api and OPENAI_API_KEY:
        print(f"\nAttempting to find hero image with keywords: {hero_keywords}")
        hero_image_url = find_image_on_unsplash(hero_keywords)
        if hero_image_url:
            print(f"Test Hero Image URL: {hero_image_url}")
        else:
            print("Failed to find a test hero image.")
    else:
        print("Skipping Unsplash hero image test due to missing API keys or keyword generation failure.")

    # Test combined function
    if unsplash_api and OPENAI_API_KEY:
        print("\nTesting get_image_for_element...")
        combined_image_url = get_image_for_element(test_style, "company values infographic background")
        if combined_image_url:
            print(f"Test Combined Function Image URL: {combined_image_url}")
        else:
            print("Failed to get image via combined function.")
    else:
        print("Skipping get_image_for_element test due to missing API keys.")

    print("\nImage Agent testing complete.")

