import google.generativeai as genai
import os
from PIL import Image
import io

def is_disaster_image(image_data):
    """
    Analyzes an image using the Gemini API to determine if it is disaster-related.

    Args:
        image_data (bytes): The binary data of the image.

    Returns:
        bool: True if the image is disaster-related, False otherwise.
    """
    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("Error: GEMINI_API_KEY not found in environment variables.")
            return False

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Convert image data to a PIL Image object
        image = Image.open(io.BytesIO(image_data))

        # The prompt for the model
        prompt = "Is this image related to a natural disaster (like a flood, fire, earthquake, etc.)? Please answer with only 'Yes' or 'No'."

        # Ask the model
        response = model.generate_content([prompt, image])

        # Check the response
        result = response.text.strip().lower()
        print(f"Gemini API response: {result}")

        return 'yes' in result

    except Exception as e:
        print(f"An error occurred during image analysis: {e}")
        return False
