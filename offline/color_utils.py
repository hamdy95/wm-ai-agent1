import os
import re
import random
import json
import colorsys
from typing import Dict, List, Tuple, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure OpenAI API
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key:
    client = OpenAI(api_key=openai_api_key)
    print("OpenAI API key configured for color palette generation.")
else:
    print("Warning: OpenAI API key not found. Advanced color palette generation will not be available.")
    client = None

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join([c*2 for c in hex_color])
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color"""
    return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'

def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    """Convert HSV to RGB tuple"""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

def extract_color_from_description(description: str) -> Optional[Tuple[int, int, int]]:
    """Extract a primary color from the style description"""
    # Common color names and their hex values
    color_map = {
        'red': '#FF0000',
        'blue': '#0000FF',
        'green': '#00FF00',
        'yellow': '#FFFF00',
        'orange': '#FFA500',
        'purple': '#800080',
        'pink': '#FFC0CB',
        'brown': '#A52A2A',
        'black': '#000000',
        'white': '#FFFFFF',
        'gray': '#808080',
        'grey': '#808080',
        'gold': '#FFD700',
        'silver': '#C0C0C0',
        'navy': '#000080',
        'teal': '#008080',
        'cyan': '#00FFFF',
        'magenta': '#FF00FF',
        'lime': '#00FF00',
        'maroon': '#800000',
        'olive': '#808000',
        'aqua': '#00FFFF',
        'dark blue': '#00008B',
        'light blue': '#ADD8E6',
        'dark green': '#006400',
        'light green': '#90EE90',
        'dark red': '#8B0000',
        'light red': '#FFCCCB',
        'dark purple': '#301934',
        'light purple': '#D8BFD8',
        'turquoise': '#40E0D0',
        'lavender': '#E6E6FA',
        'indigo': '#4B0082',
        'violet': '#8F00FF',
        'beige': '#F5F5DC',
        'coral': '#FF7F50',
        'crimson': '#DC143C',
        'fuchsia': '#FF00FF',
        'dark orange': '#FF8C00',
        'dark yellow': '#DAA520',
        'baby blue': '#89CFF0',
        'baby pink': '#FFC0CB',
        'baby green': '#90EE90'
    }
    
    # Check for hex color in the description
    hex_pattern = r'#(?:[0-9a-fA-F]{3}){1,2}\b'
    hex_match = re.search(hex_pattern, description)
    if hex_match:
        hex_color = hex_match.group(0)
        return hex_to_rgb(hex_color)
    
    # Check for color names in the description
    description = description.lower()
    for color_name, hex_value in color_map.items():
        if color_name in description:
            return hex_to_rgb(hex_value)
    
    # Default to a blue color if no color is found
    return (41, 137, 206)  # Default blue color #2989CE

def generate_color_palette_with_gpt4o(style_description: str) -> Tuple[Dict[str, Tuple[int, int, int]], Dict[str, str]]:
    """Generate a complete color palette and Elementor mapping using GPT-4o based on style description"""
    if not client:
        print("Warning: OpenAI API key not available. Falling back to algorithmic palette generation.")
        primary_color = extract_color_from_description(style_description)
        palette = generate_color_palette_algorithmic(primary_color)
        return palette, None
    
    try:
        # Create a prompt for GPT-4o to generate a color palette and Elementor mapping
        prompt = f"""
        I need a professional color palette and Elementor property mapping for a website with the following style description: "{style_description}"
        
        Part 1: Please generate a complete color palette in the requested color in style description do not make another color just the requested one and make the pallate for it with the following colors (in hex format):
        - primary: The main brand color (use a rich, vibrant color that matches the style description, NOT white or very light colors)
        - primary_dark: A darker version of the primary color
        - primary_light: A lighter version of the primary color
        - secondary: A complementary or contrasting color
        - secondary_dark: A darker version of the secondary color
        - accent: An accent color for highlights and call-to-actions
        - accent_dark: A darker version of the accent color
        - neutral_light: A light neutral color for backgrounds (but not white)
        - neutral_dark: A dark neutral color for borders and separators
        - text_primary: A color for primary text that ensures good contrast with the background colors
        - text_secondary: A color for secondary text that ensures good contrast with the background colors
        - success: A color indicating success
        - warning: A color indicating warning
        - error: A color indicating error
        - white: Pure white (#FFFFFF)
        - black: Pure black (#000000)
           
        Note : Make the links color to be color far from the primary color to have a good apprearance     
        Part 2: Now, create a mapping of Elementor color properties to the palette colors above. This determines which palette color is used for each Elementor property. Include these Elementor properties:
        - background_color: Use primary or another rich color from the palette, NOT white or very light colors
        - background_overlay_color: Use primary_dark or another rich color from the palette
        - background_hover_color: Use primary_light or another appropriate color
        - background_active_color: Use secondary or another appropriate color
        - background_selected_color: Use secondary_dark or another appropriate color
        - title_color: Use black depending on the background color to ensure readability
        - description_color: Use text_secondary, white, or black depending on the background color to ensure readability
        - color_text: Use text_primary, white, or black depending on the background color to ensure readability
        - color: Use text_primary, white, or black depending on the background color to ensure readability
        - hover_color: Use accent or another appropriate color
        - active_color: Use accent_dark or another appropriate color
        - selected_color: Use accent or secondary depending on the design
        - button_background_color: Use primary, accent, or another appropriate color
        - button_hover_background_color: Use primary_dark, accent_dark, or another appropriate color
        - button_text_color: Use white or black depending on the button background to ensure readability
        - button_hover_text_color: Use white or black depending on the button hover background to ensure readability
        - border_color: Use neutral_dark or another appropriate color
        - border_hover_color: Use primary or accent depending on the design
        - primary_color: Use primary
        - secondary_color: Use secondary
        - icon_color: Use primary, accent, or text_primary depending on the background
        - icon_hover_color: Use primary_dark, accent_dark, or another appropriate color
        - heading_color: Use text_primary, white, or black depending on the background color to ensure readability
        - text_color: Use text_primary, white, or black depending on the background color to ensure readability
        - link_color: Use color to be diffrent to primary to have good appearance
        - link_hover_color: Use primary_dark or accent_dark
        - field_background_color: Use neutral_light or white depending on the design
        - field_border_color: Use neutral_dark or primary
        - field_text_color: Use text_primary or black depending on the field background
        - field_focus_border_color: Use primary or accent
        
        Return a JSON object with two properties: 'palette' containing the color palette, and 'elementor_mapping' containing the mapping of Elementor properties to palette color names.
        """
        
        # Call the OpenAI API with GPT-4o
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a professional color palette generator based on the color user will request if he said yellow generate based on that if said green same thing and so on of all colors. Respond only with valid JSON containing the requested data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=3000
        )
        
        # Extract the JSON response
        result_json = response.choices[0].message.content
        
        # Clean up the response to ensure it's valid JSON
        # Remove markdown code blocks if present
        result_json = re.sub(r'^```(json)?', '', result_json)
        result_json = re.sub(r'```$', '', result_json)
        result_json = result_json.strip()
        
        print(f"Raw JSON response from GPT-4o: {result_json[:100]}...")
        
        try:
            # Parse the JSON into a dictionary
            result_data = json.loads(result_json)
            
            # Extract palette and mapping
            palette_hex = result_data.get('palette', {})
            elementor_mapping = result_data.get('elementor_mapping', {})
            
            # Validate the palette - make sure all values are valid hex colors
            for color_name, hex_value in list(palette_hex.items()):
                if not re.match(r'^#[0-9A-Fa-f]{6}$', hex_value):
                    print(f"Warning: Invalid hex color '{hex_value}' for '{color_name}'. Fixing format.")
                    # Try to fix common issues
                    fixed_hex = re.sub(r'[^0-9A-Fa-f]', '', hex_value)
                    if len(fixed_hex) >= 6:
                        fixed_hex = '#' + fixed_hex[:6]
                        palette_hex[color_name] = fixed_hex
                        print(f"  Fixed to: {fixed_hex}")
                    else:
                        # Remove invalid colors
                        del palette_hex[color_name]
                        print(f"  Removed invalid color {color_name}")
            
            # Convert color names to hex values in elementor_mapping
            for prop, color_value in list(elementor_mapping.items()):
                # If the value is a color name from the palette, replace it with the hex value
                if color_value in palette_hex:
                    elementor_mapping[prop] = palette_hex[color_value]
                    print(f"  Converted {prop}: {color_value} → {palette_hex[color_value]}")
                # If it's not a valid hex color and not in the palette, try to fix or remove it
                elif not re.match(r'^#[0-9A-Fa-f]{6}$', color_value):
                    print(f"Warning: Elementor mapping for '{prop}' references non-existent palette color '{color_value}'. Using default.")
                    # Use primary color as default if available
                    if 'primary' in palette_hex:
                        elementor_mapping[prop] = palette_hex['primary']
                        print(f"  Using primary color {palette_hex['primary']} for {prop}")
                    else:
                        # Remove the mapping if we can't fix it
                        del elementor_mapping[prop]
                        print(f"  Removed invalid mapping for {prop}")
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from GPT-4o: {str(e)}")
            # Try to extract JSON from the response using regex
            json_match = re.search(r'\{[\s\S]*\}', result_json)
            if json_match:
                try:
                    result_data = json.loads(json_match.group(0))
                    palette_hex = result_data.get('palette', {})
                    elementor_mapping = result_data.get('elementor_mapping', {})
                    print("Successfully extracted JSON using regex fallback")
                    
                    # Validate palette hex values
                    for color_name, hex_value in list(palette_hex.items()):
                        if not re.match(r'^#[0-9A-Fa-f]{6}$', hex_value):
                            print(f"Warning: Invalid hex color '{hex_value}' for '{color_name}'. Fixing format.")
                            fixed_hex = re.sub(r'[^0-9A-Fa-f]', '', hex_value)
                            if len(fixed_hex) >= 6:
                                fixed_hex = '#' + fixed_hex[:6]
                                palette_hex[color_name] = fixed_hex
                                print(f"  Fixed to: {fixed_hex}")
                            else:
                                del palette_hex[color_name]
                                print(f"  Removed invalid color {color_name}")
                    
                    # Convert color names to hex values in elementor_mapping
                    for prop, color_value in list(elementor_mapping.items()):
                        if color_value in palette_hex:
                            elementor_mapping[prop] = palette_hex[color_value]
                            print(f"  Converted {prop}: {color_value} → {palette_hex[color_value]}")
                        elif not re.match(r'^#[0-9A-Fa-f]{6}$', color_value):
                            print(f"Warning: Elementor mapping for '{prop}' references non-existent palette color '{color_value}'. Using default.")
                            if 'primary' in palette_hex:
                                elementor_mapping[prop] = palette_hex['primary']
                                print(f"  Using primary color {palette_hex['primary']} for {prop}")
                            else:
                                del elementor_mapping[prop]
                                print(f"  Removed invalid mapping for {prop}")
                except:
                    raise Exception("Failed to parse JSON even with regex fallback")
            else:
                raise Exception("Could not find JSON object in GPT-4o response")
        
        # Convert hex colors to RGB tuples
        palette_rgb = {key: hex_to_rgb(value) for key, value in palette_hex.items()}
        
        print(f"Successfully generated color palette and Elementor mapping with GPT-4o for style: '{style_description}'")
        return palette_rgb, elementor_mapping
        
    except Exception as e:
        print(f"Error generating palette with GPT-4o: {str(e)}. Falling back to algorithmic generation.")
        primary_color = extract_color_from_description(style_description)
        palette = generate_color_palette_algorithmic(primary_color)
        return palette, None

def generate_color_palette_algorithmic(primary_color: Tuple[int, int, int]) -> Dict[str, Tuple[int, int, int]]:
    """Generate a complete color palette from a primary color using algorithmic methods"""
    h, s, v = colorsys.rgb_to_hsv(*[x/255.0 for x in primary_color])
    
    palette = {
        'primary': primary_color,
        'primary_dark': hsv_to_rgb(h, s * 1.1, v * 0.85),  # Darker version of primary
        'primary_light': hsv_to_rgb(h, s * 0.7, min(1.0, v * 1.15)),  # Lighter version of primary
        'secondary': hsv_to_rgb((h + 0.33) % 1, s, v),  # Triadic
        'secondary_dark': hsv_to_rgb((h + 0.33) % 1, s * 1.1, v * 0.85),  # Darker secondary
        'accent': hsv_to_rgb((h + 0.16) % 1, s * 0.8, v),  # Split-complementary
        'accent_dark': hsv_to_rgb((h + 0.16) % 1, s * 0.9, v * 0.75),  # Darker accent
        'neutral_light': hsv_to_rgb(h, s * 0.1, v * 0.95),  # Light neutral
        'neutral_dark': hsv_to_rgb(h, s * 0.2, v * 0.2),  # Dark neutral
        'text_primary': hsv_to_rgb(h, s * 0.05, 0.1),  # Very dark for text
        'text_secondary': hsv_to_rgb(h, s * 0.05, 0.4),  # Medium dark for secondary text
        'success': hsv_to_rgb(0.33, s * 0.7, v * 0.8),  # Green tones
        'warning': hsv_to_rgb(0.13, s * 0.8, v * 0.9),  # Orange tones
        'error': hsv_to_rgb(0.0, s * 0.8, v * 0.8),      # Red tones
        'white': (255, 255, 255)  # Pure white
    }
    
    return palette

# Rename the original function to maintain backward compatibility
def generate_color_palette(primary_color: Tuple[int, int, int]) -> Dict[str, Tuple[int, int, int]]:
    """Generate a complete color palette from a primary color (legacy method)"""
    return generate_color_palette_algorithmic(primary_color)

# Mapping of Elementor color properties to our palette colors
ELEMENTOR_COLOR_PROPERTIES = {
    # Background Colors
    'background_color': 'primary',
    'background_overlay_color': 'primary_dark',
    'background_hover_color': 'primary_light',
    'background_active_color': 'secondary',
    'background_selected_color': 'secondary_dark',
    
    # Column Colors
    'column_background_color': 'primary',
    '_background_color': 'primary',  # Used by columns
    '_background_hover_color': 'primary_light',
    '_background_overlay_color': 'primary_dark',
    'column_text_color': 'text_primary',
    
    # Text Colors  
    'title_color': 'text_primary',
    'description_color': 'text_secondary',
    'color_text': 'text_primary',
    'color': 'text_primary',
    'heading_color': 'text_primary',
    'text_color': 'text_primary',
    'hover_color': 'accent',
    'active_color': 'accent',
    'selected_color': 'accent',
    
    # Button Colors
    'button_background_color': 'primary',
    'button_hover_background_color': 'primary_dark',
    'button_text_color': 'white',
    'button_hover_text_color': 'white',
    
    # Border Colors
    'border_color': 'neutral_light',
    'border_hover_color': 'primary',
    
    # Icon Colors
    'primary_color': 'primary',
    'secondary_color': 'secondary',
    'icon_color': 'accent',
    'icon_hover_color': 'accent_dark',
    
    # Section Colors
    'link_color': 'accent',
    'link_hover_color': 'accent_dark',
    
    # Form Colors
    'field_background_color': 'neutral_light',
    'field_border_color': 'primary',
    'field_text_color': 'neutral_dark',
    'field_focus_border_color': 'accent'
}

def map_colors_to_elementor(palette: Dict[str, Tuple[int, int, int]], custom_mapping: Dict[str, str] = None) -> Dict[str, str]:
    """Map our palette colors to Elementor properties using custom mapping if provided"""
    elementor_colors = {}
    
    # Convert palette RGB tuples to hex strings
    hex_palette = {key: rgb_to_hex(value) for key, value in palette.items()}
    
    # Use custom mapping if provided, otherwise use the default mapping
    mapping = custom_mapping if custom_mapping else ELEMENTOR_COLOR_PROPERTIES
    
    # Map each Elementor property to its corresponding palette color
    for elementor_prop, palette_color in mapping.items():
        if palette_color in hex_palette:
            elementor_colors[elementor_prop] = hex_palette[palette_color]
    
    # If we're using a custom mapping but some properties are missing, fill them in with defaults
    if custom_mapping:
        for elementor_prop, palette_color in ELEMENTOR_COLOR_PROPERTIES.items():
            if elementor_prop not in elementor_colors and palette_color in hex_palette:
                elementor_colors[elementor_prop] = hex_palette[palette_color]
                print(f"Added default mapping for {elementor_prop} -> {palette_color}")
    
    return elementor_colors

def create_color_mapping(original_colors: List[str], style_description: str) -> Dict[str, str]:
    """Create a mapping from original colors to new palette colors using GPT-4o if available"""
    # Generate color palette and mapping using GPT-4o if available
    try:
        # First try to generate a palette and mapping with GPT-4o
        palette, custom_mapping = generate_color_palette_with_gpt4o(style_description)
        if custom_mapping:
            print("Using GPT-4o generated color palette and Elementor mapping for enhanced color mapping.")
        else:
            print("Using GPT-4o generated color palette with default Elementor mapping.")
    except Exception as e:
        # Fall back to algorithmic method if GPT-4o fails
        print(f"Falling back to algorithmic color palette generation: {str(e)}")
        primary_color = extract_color_from_description(style_description)
        palette = generate_color_palette_algorithmic(primary_color)
        custom_mapping = None
    
    # Get Elementor color mapping using the custom mapping if available
    elementor_colors = map_colors_to_elementor(palette, custom_mapping)
    
    # Validate all hex colors in elementor_colors to ensure they're valid
    for prop, color in list(elementor_colors.items()):
        if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
            print(f"Warning: Invalid hex color '{color}' in elementor_colors for '{prop}'. Fixing format.")
            # Try to fix common issues
            fixed_hex = re.sub(r'[^0-9A-Fa-f]', '', color)
            if len(fixed_hex) >= 6:
                fixed_hex = '#' + fixed_hex[:6]
                elementor_colors[prop] = fixed_hex
                print(f"  Fixed to: {fixed_hex}")
            else:
                # Remove invalid colors
                del elementor_colors[prop]
                print(f"  Removed invalid mapping for {prop}")
    
    # Create a mapping from original colors to new colors
    color_map = {}
    
    # If we have very few original colors, map them directly to our palette
    if len(original_colors) <= len(palette):
        palette_hex = [rgb_to_hex(color) for color in palette.values()]
        for i, original in enumerate(original_colors):
            if i < len(palette_hex):
                color_map[original] = palette_hex[i]
    else:
        # For each original color, find the closest match in our palette
        # This is a simplified approach - in a real system you might want to use color distance
        palette_hex = {key: rgb_to_hex(value) for key, value in palette.items()}
        
        # First, handle specific Elementor properties if we can identify them
        for original in original_colors:
            # Try to find this color in Elementor properties
            for prop, color in elementor_colors.items():
                if prop in original.lower():
                    color_map[original] = color
                    break
        
        # For any remaining colors, distribute them among our palette
        remaining = [c for c in original_colors if c not in color_map]
        palette_values = list(palette_hex.values())
        for i, original in enumerate(remaining):
            color_map[original] = palette_values[i % len(palette_values)]
    
    # Validate all hex colors in color_map to ensure they're valid
    for original, color in list(color_map.items()):
        if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
            print(f"Warning: Invalid hex color '{color}' in color_map for '{original}'. Fixing format.")
            # Try to fix common issues
            fixed_hex = re.sub(r'[^0-9A-Fa-f]', '', color)
            if len(fixed_hex) >= 6:
                fixed_hex = '#' + fixed_hex[:6]
                color_map[original] = fixed_hex
                print(f"  Fixed to: {fixed_hex}")
            else:
                # Use a default color
                color_map[original] = '#FF0000'  # Default to red
                print(f"  Using default color #FF0000 for {original}")
    
    # Print the Elementor color mapping for debugging
    print("\nElementor color mapping:")
    for prop, color in elementor_colors.items():
        print(f"  {prop}: {color}")
    
    return color_map, {key: rgb_to_hex(value) for key, value in palette.items()}
