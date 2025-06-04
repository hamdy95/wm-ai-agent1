import json
import xml.etree.ElementTree as ET
import os
import re
import sys

# Add the offline directory to the path so we can import color_utils and image_agent
sys.path.append(os.path.join(os.path.dirname(__file__), 'offline'))

# Check if color_utils is available
try:
    # First try direct import after adding the path
    from color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping
    print("Successfully imported color_utils directly.")
except ImportError:
    try:
        # Fall back to qualified import
        from offline.color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping
        print("Successfully imported color_utils with offline prefix.")
    except ImportError:
        print("Warning: Could not import color_utils. Color mapping will use legacy method.")

# Check if image_agent is available
IMAGE_AGENT_AVAILABLE = False
try:
    # First try direct import after adding the path
    from offline.image_agent import get_image_for_element
    # Check if required environment variables are set
    if os.getenv("UNSPLASH_ACCESS_KEY") and os.getenv("OPENAI_API_KEY"):
        IMAGE_AGENT_AVAILABLE = True
        print("Image Agent is available for image replacement.")
    else:
        print("Warning: Image Agent is available but required API keys are missing.")
except ImportError:
    try:
        # Fall back to qualified import
        from offline.image_agent import get_image_for_element
        # Check if required environment variables are set
        if os.getenv("UNSPLASH_ACCESS_KEY") and os.getenv("OPENAI_API_KEY"):
            IMAGE_AGENT_AVAILABLE = True
            print("Image Agent is available for image replacement (with offline prefix).")
        else:
            print("Warning: Image Agent is available but required API keys are missing.")
    except ImportError:
        print("Warning: Could not import image_agent. Image replacement will not be available.")


def remove_control_characters(s):
    """Remove control characters from a string, except for tab, newline, carriage return."""
    if not isinstance(s, str):
        return s
    # Allow \t (tab), \n (newline), \r (carriage return)
    # Remove characters in ranges \x00-\x08, \x0b-\x0c, \x0e-\x1f, and \x7f (DEL)
    # The regex r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]' is used here.
    # In the JSON string, backslashes in the regex pattern need to be escaped (e.g., \x00 becomes \\x00).
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)


def replace_with_images(xml_file_path, json_file_path, output_file_path, verbose_debug=True):
    """
    A wrapper around replace_text_and_colors that ensures image replacement is enabled.
    This function reads the transformation data, sets replace_images=True, and then calls replace_text_and_colors.
    
    Args:
        xml_file_path: Path to the XML file to process
        json_file_path: Path to the JSON file with transformation data
        output_file_path: Path to write the output XML file
        verbose_debug: Whether to print verbose debug information
    """
    if not IMAGE_AGENT_AVAILABLE:
        print("WARNING: Image Agent is not available. Cannot replace images.")
        print("Make sure you have the following in your .env file:\n- UNSPLASH_ACCESS_KEY\n- UNSPLASH_SECRET_KEY\n- OPENAI_API_KEY")
        print("And make sure you have python-unsplash installed: pip install python-unsplash>=1.0.0")
        return replace_text_and_colors(xml_file_path, json_file_path, output_file_path, verbose_debug)
    
    print("\n==== IMAGE REPLACEMENT MODE ENABLED ====")
    print(f"Image Agent is available and will replace images in {xml_file_path}")
    
    try:
        # Read the transformation data
        with open(json_file_path, 'r', encoding='utf-8') as f:
            transform_data = json.load(f)
        
        # Add replace_images flag if not already present
        transform_data['replace_images'] = True
        
        # Ensure style_description is present for image context
        if 'style_description' not in transform_data:
            if 'description' in transform_data:
                transform_data['style_description'] = transform_data['description']
            else:
                print("WARNING: No style_description found in transformation data. Using default.")
                transform_data['style_description'] = "modern professional design"
        
        print(f"Using style description: '{transform_data['style_description']}'")
        
        # Write the updated transformation data back
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(transform_data, f, indent=2)
        
        # Call replace_text_and_colors with replace_images=True
        return replace_text_and_colors(xml_file_path, json_file_path, output_file_path, verbose_debug, replace_images=True)
    except Exception as e:
        print(f"Error setting up image replacement: {e}")
        # Fall back to regular replacement without images
        return replace_text_and_colors(xml_file_path, json_file_path, output_file_path, verbose_debug)


def extract_colors(color_data):
    """Extract colors from a list of color transformations that might be JSON strings"""
    color_map = {}
    
    for item in color_data:
        try:
            # If the item is a JSON string with escaped quotes
            if isinstance(item, str):
                # Remove any unnecessary escaping
                item = item.replace('\\"', '"').strip('"')
                
                # Parse the JSON object
                if item.startswith('{'):
                    color_obj = json.loads(item)
                    if 'from' in color_obj and 'to' in color_obj:
                        from_color = color_obj['from'].upper()
                        to_color = color_obj['to'].upper()
                        # Only add if they're different
                        if from_color != to_color:
                            color_map[from_color] = to_color
                    # Simple format without from/to
                    elif 'original' in color_obj and 'transformed' in color_obj:
                        from_color = color_obj['original'].upper()
                        to_color = color_obj['transformed'].upper()
                        if from_color != to_color:
                            color_map[from_color] = to_color
            
            # If the item is already a dictionary
            elif isinstance(item, dict):
                if 'from' in item and 'to' in item:
                    from_color = item['from'].upper()
                    to_color = item['to'].upper()
                    if from_color != to_color:
                        color_map[from_color] = to_color
                elif 'original' in item and 'transformed' in item:
                    from_color = item['original'].upper()
                    to_color = item['transformed'].upper()
                    if from_color != to_color:
                        color_map[from_color] = to_color
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"Error processing color: {item}, error: {e}")
            # Try to extract hex colors directly if JSON parsing fails
            if isinstance(item, str):
                # Find hex color codes
                hex_colors = re.findall(r'#[0-9A-Fa-f]{3,6}', item)
                if len(hex_colors) == 2:
                    from_color = hex_colors[0].upper()
                    to_color = hex_colors[1].upper()
                    if from_color != to_color:
                        color_map[from_color] = to_color
            continue
    
    # Convert all colors to uppercase for case-insensitive matching
    return {k.upper(): v.upper() for k, v in color_map.items() if k != v}

def scan_background_colors(elementor_data):
    """Scan background colors but don't preserve white backgrounds"""
    # Return an empty dictionary to prevent preserving white backgrounds
    # This allows the color mapping to apply to all backgrounds
    return {}

def process_elementor_data(elementor_data, generic_color_map, white_bg_colors, specific_palette_map=None):
    """Process colors in Elementor data using color mappings."""
    if specific_palette_map:
        print(f"INFO: process_elementor_data called with specific_palette_map (size: {len(specific_palette_map)}) and generic_color_map (size: {len(generic_color_map)}).") 
    else:
        print(f"INFO: process_elementor_data called with ONLY generic_color_map (size: {len(generic_color_map)}). specific_palette_map is None.")

    modified_data = []
    # Keep track of actual replacements made by this function
    replacements_from_specific_map = 0
    replacements_from_generic_map = 0

    def process_element(element):
        nonlocal modified_data
        nonlocal replacements_from_specific_map
        nonlocal replacements_from_generic_map
        if isinstance(element, dict):
            if 'settings' in element and 'id' in element:
                settings = element['settings']
                element_id = element['id']
                
                # Process all colors including backgrounds and text colors
                if isinstance(settings, dict):
                    # Check if this is a column element
                    is_column = element.get('elType') == 'column'
                    
                    for setting_key in list(settings.keys()):
                        value = settings[setting_key]
                        if isinstance(value, str):
                            # Check if the value looks like a color code
                            if re.match(r'^#[0-9A-Fa-f]{3,6}$', value) or value.lower() in ['white', 'black', 'red', 'blue', 'green', 'yellow']:
                                # Special handling for column backgrounds and text
                                if is_column:
                                    if '_background_color' in setting_key:
                                        # Force column backgrounds to use primary color
                                        if specific_palette_map and 'primary' in specific_palette_map:
                                            settings[setting_key] = specific_palette_map['primary']
                                            # Set text color to white for contrast
                                            settings['color'] = '#FFFFFF'
                                            settings['text_color'] = '#FFFFFF'
                                            settings['title_color'] = '#FFFFFF'
                                            continue
                                
                                # First try to map based on Elementor property name if we have elementor_color_map
                                if specific_palette_map and setting_key in specific_palette_map:
                                    # Use the property-based mapping from our color system
                                    new_color = specific_palette_map[setting_key].upper()
                                    if not re.fullmatch(r'^#[0-9A-F]{6}$', new_color):
                                        print(f"WARNING: Invalid hex '{new_color}' from specific_palette_map for '{setting_key}'. Original: '{value}'. Attempting to fix.")
                                        # Try to fix common issues
                                        fixed_hex = re.sub(r'[^0-9A-F]', '', new_color)
                                        if len(fixed_hex) >= 6:
                                            fixed_hex = '#' + fixed_hex[:6].upper()
                                            new_color = fixed_hex
                                            print(f"  Fixed to: {fixed_hex}")
                                        else:
                                            print(f"  Could not fix hex color. Skipping.")
                                            continue
                                        
                                    if value.upper() != new_color:
                                        settings[setting_key] = new_color
                                        print(f"Replaced color: {value} -> {new_color} in {setting_key} (using specific_palette_map)")
                                        replacements_from_specific_map += 1
                                else:
                                    # For background-related keys, always apply the mapping
                                    if any(bg in setting_key.lower() for bg in ['background', 'bg_']):
                                        value_upper = value.upper()
                                        if value_upper in generic_color_map:
                                                new_color = generic_color_map[value_upper].upper()
                                                if not re.fullmatch(r'^#[0-9A-F]{6}$', new_color):
                                                    print(f"WARNING: Invalid hex '{new_color}' from generic_color_map for original '{value_upper}' (key: '{setting_key}'). Attempting to fix.")
                                                    # Try to fix common issues
                                                    fixed_hex = re.sub(r'[^0-9A-F]', '', new_color)
                                                    if len(fixed_hex) >= 6:
                                                        fixed_hex = '#' + fixed_hex[:6].upper()
                                                        new_color = fixed_hex
                                                        print(f"  Fixed to: {fixed_hex}")
                                                    else:
                                                        print(f"  Could not fix hex color. Skipping.")
                                                        continue
                                                    
                                                if value_upper != new_color:
                                                    settings[setting_key] = new_color
                                                    print(f"Replaced color: {value_upper} -> {new_color} in {setting_key} (using generic_color_map)")
                                                    nonlocal replacements_from_generic_map
                                                    replacements_from_generic_map += 1
                                    # For non-background colors, replace normally
                                    else:
                                        value_upper = value.upper()
                                        if value_upper in generic_color_map:
                                            new_color = generic_color_map[value_upper].upper()
                                            if not re.fullmatch(r'^#[0-9A-F]{6}$', new_color):
                                                print(f"WARNING: Invalid hex '{new_color}' from generic_color_map for original '{value_upper}' (key: '{setting_key}'). Attempting to fix.")
                                                # Try to fix common issues
                                                fixed_hex = re.sub(r'[^0-9A-F]', '', new_color)
                                                if len(fixed_hex) >= 6:
                                                    fixed_hex = '#' + fixed_hex[:6].upper()
                                                    new_color = fixed_hex
                                                    print(f"  Fixed to: {fixed_hex}")
                                                else:
                                                    print(f"  Could not fix hex color. Skipping.")
                                                    continue
                                            
                                            if value_upper != new_color:
                                                settings[setting_key] = new_color
                                                print(f"Replaced color: {value_upper} -> {new_color} in {setting_key} (using generic_color_map)")
                                                replacements_from_generic_map += 1
            
            # Process nested elements
            if 'elements' in element and isinstance(element['elements'], list):
                for child in element['elements']:
                    process_element(child)
                    
    if isinstance(elementor_data, list):
        for item in elementor_data:
            process_element(item)
    else:
        process_element(elementor_data)
    
    print(f"INFO: Total replacements from specific_palette_map: {replacements_from_specific_map}")
    print(f"INFO: Total replacements from generic_color_map: {replacements_from_generic_map}")
    return elementor_data

def extract_text(text_item):
    """Extract original and transformed text from a text transformation item that might be a JSON string"""
    original = None
    transformed = None
    
    try:
        # If it's a string that looks like JSON
        if isinstance(text_item, str):
            # Clean up potential escape issues
            if text_item.startswith('"') and text_item.endswith('"'):
                text_item = text_item[1:-1]
            
            text_item = text_item.replace('\\"', '"')
            
            # Try to parse as JSON
            if text_item.startswith('{'):
                try:
                    obj = json.loads(text_item)
                    if isinstance(obj, dict):
                        if 'original' in obj and 'transformed' in obj:
                            original = obj['original']
                            transformed = obj['transformed']
                except json.JSONDecodeError as e:
                    print(f"JSON decode error in extract_text: {e}")
                    # Try regex as fallback for original/transformed format
                    orig_match = re.search(r'"original"\s*:\s*"([^"]+)"', text_item)
                    trans_match = re.search(r'"transformed"\s*:\s*"([^"]+)"', text_item)
                    if orig_match and trans_match:
                        original = orig_match.group(1)
                        transformed = trans_match.group(1)
        
        # If it's already a dictionary
        elif isinstance(text_item, dict):
            if 'original' in text_item and 'transformed' in text_item:
                original = text_item['original']
                transformed = text_item['transformed']
    
    except Exception as e:
        print(f"Error in extract_text: {e}")
    
    # If extraction worked and values are different
    if original and transformed and original != transformed:
        return original, transformed
    
    # Fallback: return the item itself as both original and transformed
    if isinstance(text_item, str):
        return text_item, text_item
    return None, None

def replace_text_and_colors(xml_file_path, json_file_path, output_file_path, verbose_debug=True, replace_images=False):
    print(f"Starting replacement process for {xml_file_path}")
    # Register namespaces for WordPress XML
    ET.register_namespace('wp', 'http://wordpress.org/export/1.2/')
    ET.register_namespace('excerpt', 'http://wordpress.org/export/1.2/excerpt/')
    ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
    ET.register_namespace('wfw', 'http://wellformedweb.org/CommentAPI/')
    ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
    
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    
    print(f"Loading transformation data from {json_file_path}")
    with open(json_file_path, 'r', encoding='utf-8') as json_file:
        data = json.load(json_file)
    
    # Save a copy of raw transformation data for debugging
    debug_dir = os.path.join(os.path.dirname(output_file_path), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    with open(os.path.join(debug_dir, "raw_transforms.json"), 'w', encoding='utf-8') as debug_file:
        json.dump(data, debug_file, indent=2)
    
    # If verbose debug, collect all text in the XML for analysis
    if verbose_debug:
        all_xml_texts = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                if len(elem.text.strip()) > 10:  # Only collect meaningful text
                    all_xml_texts.append(elem.text.strip())
        
        # Write all texts to a debug file
        with open(os.path.join(debug_dir, "all_xml_texts.json"), 'w', encoding='utf-8') as debug_file:
            json.dump(all_xml_texts, debug_file, indent=2)
        print(f"Collected {len(all_xml_texts)} text elements from XML for debugging")
    
    # Extract and process text transformations
    text_transformations = data.get("text_transformations", [])
    print(f"Found {len(text_transformations)} raw text transformations")
    
    # Extract processed text transformations
    processed_text_transformations = []
    for item in text_transformations:
        # Handle the case where the text is stored directly, not as original/transformed pairs
        if isinstance(item, str):
            # If this is just a direct text replacement, we need to find a match in the original content
            for elem in root.iter():
                if elem.text and item in elem.text:
                    processed_text_transformations.append((item, item))
                    print(f"Found direct text match: '{item[:30]}...'")
                    break
            continue
        
        # Handle dictionary format with original/transformed fields
        if isinstance(item, dict) and "original" in item and "transformed" in item:
            original = item["original"]
            transformed = item["transformed"]
            if original and transformed and original != transformed:
                processed_text_transformations.append((original, transformed))
                print(f"Added text transformation: '{original[:30]}...' -> '{transformed[:30]}...'")
            continue
            
        # Otherwise try to extract from JSON-encoded strings
        original, transformed = extract_text(item)
        if original and transformed and original != transformed:
            processed_text_transformations.append((original, transformed))
            print(f"Processed text transformation: '{original[:30]}...' -> '{transformed[:30]}...'")
    
    print(f"Extracted {len(processed_text_transformations)} valid text transformations")
    
    # Process color data - first try to use the color_palette format
    color_map = {}
    if "color_palette" in data and "original_colors" in data["color_palette"] and "new_colors" in data["color_palette"]:
        original_colors = data["color_palette"]["original_colors"]
        new_colors = data["color_palette"]["new_colors"]
        
        # Handle different color formats (string vs object)
        def get_color_value(color_item):
            if isinstance(color_item, dict) and 'hex' in color_item:
                return color_item['hex']
            elif isinstance(color_item, str):
                return color_item
            return None
        
        if len(original_colors) == len(new_colors):
            # Make sure all colors are in uppercase for consistent matching
            color_map = {}
            for o, n in zip(original_colors, new_colors):
                original = get_color_value(o)
                new = get_color_value(n)
                if original and new and original != new:
                    color_map[original.upper()] = new.upper()
            
            print(f"Created color map from color_palette with {len(color_map)} colors (this will be used as generic_color_map if specific_palette_map is not generated)")
            
        # Initialize elementor_color_map (for specific palette mapping)
        elementor_color_map = None
        # Check if we have a full_palette from our new color system
        if "full_palette" in data and isinstance(data["full_palette"], dict):
            print("INFO: Found 'full_palette' in transformation data. Attempting to create specific_palette_map.")
            try:
                if 'color_utils' in sys.modules:
                    palette_dict = {k: v for k, v in data["full_palette"].items()}
                    elementor_color_map = map_colors_to_elementor(palette_dict) # This is our specific_palette_map
                    print(f"INFO: Successfully created specific_palette_map with {len(elementor_color_map)} properties using color_utils.")
                else:
                    print("WARNING: 'color_utils' module not found in sys.modules. Cannot create specific_palette_map.")
            except Exception as e:
                print(f"ERROR: Failed to create specific_palette_map from 'full_palette': {e}")
        else:
            print("INFO: 'full_palette' not found or not a dict in transformation data. specific_palette_map will be None.")

        # Fallback to legacy color transformations if color_map is still empty
        if not color_map:
            print("color_map from color_palette is empty, trying legacy color_transformations.")
            color_transformations = data.get("color_transformations", [])
            color_map = extract_colors(color_transformations) # This becomes generic_color_map
            print(f"Created generic_color_map from legacy color_transformations with {len(color_map)} colors")
    else:
        # Fallback if no color_palette section
        print("No 'color_palette' in data, trying legacy color_transformations for generic_color_map.")
        color_transformations = data.get("color_transformations", [])
        color_map = extract_colors(color_transformations) # This becomes generic_color_map
        elementor_color_map = None # Ensure specific_palette_map is None
        print(f"Created generic_color_map from legacy color_transformations with {len(color_map)} colors. specific_palette_map is None.")
            # This can be used for more advanced color mapping if needed
    
    # If no color_palette or it was empty, try using color_transformations
    if not color_map and "color_transformations" in data:
        color_map = extract_colors(data["color_transformations"])
        print(f"Created color map from color_transformations with {len(color_map)} colors")
    
    # Save processed transformations for debugging
    with open(os.path.join(debug_dir, "processed_transforms.json"), 'w', encoding='utf-8') as debug_file:
        debug_data = {
            "text_transformations": [{"original": o, "transformed": t} for o, t in processed_text_transformations],
            "color_transformations": [{"from": k, "to": v} for k, v in color_map.items()]
        }
        json.dump(debug_data, debug_file, indent=2)
    
    text_replaced_count = 0
    color_replaced_count = 0
    
    # Replace text in the XML
    for original_text, transformed_text in processed_text_transformations:
        # Ensure transformed_text is properly quoted if it starts with a currency symbol
        safe_transformed_text = transformed_text
        if isinstance(transformed_text, str) and transformed_text.startswith('$') and not transformed_text.startswith('"$'):
            safe_transformed_text = f'"{transformed_text}"'  # Add quotes to prevent JSON parsing errors
            print(f"Adding quotes to currency value: {transformed_text} -> {safe_transformed_text}")
        
        for elem in root.iter():
            if elem.text and original_text in elem.text:
                elem.text = elem.text.replace(original_text, safe_transformed_text)
                text_replaced_count += 1
                print(f"Replaced text: '{original_text[:30]}...' -> '{safe_transformed_text[:30]}...'")
            
            if elem.tail and original_text in elem.tail:
                elem.tail = elem.tail.replace(original_text, safe_transformed_text)
                text_replaced_count += 1
            
            if elem.attrib:
                for attr_key, attr_value in elem.attrib.items():
                    if original_text in attr_value:
                        elem.attrib[attr_key] = attr_value.replace(original_text, safe_transformed_text)
                        text_replaced_count += 1
    
    print(f"Replaced {text_replaced_count} text occurrences in XML elements")
    
    # Store white background colors only
    white_colors = {}
    for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
        if item.text and '[{' in item.text:
            try:
                elementor_data = json.loads(item.text)
                page_colors = scan_background_colors(elementor_data)
                white_colors.update(page_colors)
            except json.JSONDecodeError:
                continue

    # Generate a smart color palette and mapping if we have a style description
    style_description = data.get("style_description", "")
    print(f"Transforming {len(color_map)} colors based on style description: {style_description}")

    # Generate color map and palette using GPT-4o if available
    color_map, palette_hex = create_color_mapping(list(color_map.keys()), style_description)

    # Get the Elementor color mapping (specific_palette_map) from GPT-4o
    # This maps Elementor properties to specific colors
    try:
        # Try to generate a palette and mapping with GPT-4o
        from offline.color_utils import generate_color_palette_with_gpt4o
        palette, elementor_color_map = generate_color_palette_with_gpt4o(style_description)
        if elementor_color_map:
            print(f"Using GPT-4o generated Elementor mapping with {len(elementor_color_map)} properties")
        else:
            # If GPT-4o didn't provide a mapping, use the default mapping
            from offline.color_utils import map_colors_to_elementor
            elementor_color_map = map_colors_to_elementor(palette_hex)
            print(f"Using default Elementor mapping with {len(elementor_color_map)} properties")
    except Exception as e:
        # If GPT-4o fails, fall back to the default mapping
        print(f"Falling back to default Elementor mapping: {str(e)}")
        from offline.color_utils import map_colors_to_elementor
        elementor_color_map = map_colors_to_elementor(palette_hex)
        print(f"Using default Elementor mapping with {len(elementor_color_map)} properties")

    # Validate all hex colors in elementor_color_map
    for prop, color in list(elementor_color_map.items()):
        if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
            print(f"Warning: Invalid hex color '{color}' in elementor_color_map for '{prop}'. Fixing format.")
            # Try to fix common issues
            fixed_hex = re.sub(r'[^0-9A-Fa-f]', '', color)
            if len(fixed_hex) >= 6:
                fixed_hex = '#' + fixed_hex[:6]
                elementor_color_map[prop] = fixed_hex
                print(f"  Fixed to: {fixed_hex}")
            else:
                # Use a default color
                elementor_color_map[prop] = '#FF0000'  # Default to red
                print(f"  Using default color #FF0000 for {prop}")

    # For debugging, print out the elementor_color_map
    print(f"Using Elementor color mapping with {len(elementor_color_map)} properties for process_elementor_data")

    # Process XML with preserved white backgrounds
    elementor_text_replaced = 0
    image_replaced_count = 0
    for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
        if item.text and '[{' in item.text:
            try:
                raw_elementor_json_text = item.text
                sanitized_elementor_json_text = remove_control_characters(raw_elementor_json_text)
                
                # Fix common JSON parsing issues with currency values
                # Look for patterns like: "title": $300 (missing quotes around the value)
                sanitized_elementor_json_text = re.sub(r'"([^"]+)"\s*:\s*\$(\d+)', r'"\1": "$\2"', sanitized_elementor_json_text)
                
                elementor_data = json.loads(sanitized_elementor_json_text)
                
                # Scan for white background colors before any modification
                if processed_text_transformations:
                    def process_text_in_elementor(element):
                        nonlocal elementor_text_replaced
                        if isinstance(element, dict):
                            if 'settings' in element:
                                settings = element['settings']
                                # Check if settings is a dictionary before accessing keys
                                if not isinstance(settings, dict):
                                    return
                                
                                # Common text fields in Elementor
                                text_keys = [
                                    'title', 'heading', 'description', 'content', 'text', 
                                    'button_text', 'link_text', 'label', 'sub_title', 
                                    'caption', 'placeholder', 'before_title', 'after_title',
                                    'prefix', 'suffix', 'editor', 'html', 'message'
                                ]
                                
                                for key in list(settings.keys()):
                                    value = settings[key]
                                    if isinstance(value, str):
                                        # First check if the key itself indicates this might be a text field
                                        is_text_field = any(text_key in key.lower() for text_key in text_keys)
                                        
                                        # But also try to replace text even if not explicitly a text field
                                        # as long as it's long enough to be content rather than a setting
                                        if is_text_field or len(value) > 20:
                                            for original_text, transformed_text in processed_text_transformations:
                                                if original_text in value:
                                                    sanitized_transformed_text = remove_control_characters(transformed_text)
                                                    settings[key] = value.replace(original_text, sanitized_transformed_text)
                                                    elementor_text_replaced += 1
                                                    print(f"Replaced Elementor text in {key}: '{original_text[:30]}...' -> '{transformed_text[:30]}...'")
                            
                            # Process nested elements
                            if 'elements' in element and isinstance(element['elements'], list):
                                for child in element['elements']:
                                    process_text_in_elementor(child)
                    
                    if isinstance(elementor_data, list):
                        for element in elementor_data:
                            process_text_in_elementor(element)
                    else:
                        process_text_in_elementor(elementor_data)
                
                # Process colors in Elementor data
                if color_map:
                    # Process the Elementor data with our color mappings
                    # Use the elementor_color_map generated earlier with GPT-4o if available
                    modified_data = process_elementor_data(
                        elementor_data, 
                        generic_color_map=color_map,  # This is the map from color_palette or legacy transformations
                        white_bg_colors=white_colors, 
                        specific_palette_map=elementor_color_map # This is the map from GPT-4o via create_color_mapping
                    )
                    
                    # Process images if requested and available
                    if replace_images and IMAGE_AGENT_AVAILABLE:
                        modified_data = process_elementor_images(modified_data, data.get("style_description", ""))
                        image_replaced_count += 1
                    
                    item.text = json.dumps(modified_data)
                    color_replaced_count += 1
            except json.JSONDecodeError as e:
                print(f"Error decoding Elementor data: {e}")
                # Enhanced logging for JSONDecodeError
                error_char_index = getattr(e, 'pos', None)
                if error_char_index is not None and hasattr(sanitized_elementor_json_text, '__len__') and isinstance(sanitized_elementor_json_text, str):
                    print(f"Problematic JSON string content around character {error_char_index} (line {getattr(e, 'lineno', 'N/A')}, col {getattr(e, 'colno', 'N/A')}):")
                    start_index = max(0, error_char_index - 80) # Show 80 chars before
                    end_index = min(len(sanitized_elementor_json_text), error_char_index + 80) # Show 80 chars after
                    snippet = sanitized_elementor_json_text[start_index:end_index]
                    # Highlight the exact character if possible
                    relative_error_pos = error_char_index - start_index
                    highlighted_snippet = snippet[:relative_error_pos] + "<<ERROR_HERE>>" + snippet[relative_error_pos:]
                    print(f"SNIPPET: ...{highlighted_snippet}...\n")
                    # You can also save the full problematic string to a file for inspection:
                    # with open("debug_failed_json.txt", "w", encoding='utf-8') as f_debug:
                    #     f_debug.write(sanitized_elementor_json_text)
                    # print("Full problematic JSON string saved to debug_failed_json.txt")
                else:
                    print("Could not determine exact error position or content for JSON string.")
                continue
            except Exception as e:
                print(f"Error processing Elementor data: {str(e)}")
                continue
    
    print(f"Replaced {elementor_text_replaced} text occurrences in Elementor data")
    print(f"Processed {color_replaced_count} Elementor sections for color replacements")
    if replace_images and IMAGE_AGENT_AVAILABLE:
        print(f"Processed {image_replaced_count} Elementor sections for image replacements")
    
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    tree.write(output_file_path, encoding='utf-8', xml_declaration=True)
    print(f"Wrote modified XML to {output_file_path}")

def process_elementor_images(elementor_data, style_description):
    """
    Process images in Elementor data by replacing them with images from Unsplash.
    
    Args:
        elementor_data: The Elementor data to process
        style_description: The style description to use for image context
        
    Returns:
        The modified Elementor data with replaced images
    """
    image_replacements = 0
    
    def process_element(element):
        nonlocal image_replacements
        if isinstance(element, dict):
            if 'settings' in element and isinstance(element['settings'], dict):
                settings = element['settings']
                element_type = element.get('widgetType', element.get('elType', ''))
                element_id = element.get('id', '')
                
                # Determine the context based on element properties
                context = determine_image_context(element)
                
                # Process image widgets
                if element_type == 'image' and 'image' in settings:
                    # Get current image URL if available
                    current_url = None
                    if isinstance(settings.get('image'), dict) and 'url' in settings['image']:
                        current_url = settings['image']['url']
                    elif isinstance(settings.get('image'), str) and settings['image'].startswith('http'):
                        current_url = settings['image']
                    
                    # Get a new image
                    new_image_url = get_image_for_element(
                        style_description=style_description,
                        element_context=context,
                        element_type='image_widget',
                        current_image_url=current_url
                    )
                    
                    if new_image_url:
                        # Update the image URL
                        if isinstance(settings['image'], dict):
                            settings['image']['url'] = new_image_url
                            # Also update id to indicate it's an external image
                            settings['image']['id'] = ''
                        else:
                            settings['image'] = new_image_url
                        image_replacements += 1
                        print(f"Replaced image in element {element_id} with {new_image_url}")
                
                # Process background images
                bg_keys = ['background_image', 'background_overlay_image']
                for bg_key in bg_keys:
                    if bg_key in settings:
                        current_url = None
                        if isinstance(settings[bg_key], dict) and 'url' in settings[bg_key]:
                            current_url = settings[bg_key]['url']
                        elif isinstance(settings[bg_key], str) and settings[bg_key].startswith('http'):
                            current_url = settings[bg_key]
                        
                        # Get a new image
                        new_image_url = get_image_for_element(
                            style_description=style_description,
                            element_context=f"{context} background",
                            element_type='background_image',
                            current_image_url=current_url
                        )
                        
                        if new_image_url:
                            # Update the image URL
                            if isinstance(settings[bg_key], dict):
                                settings[bg_key]['url'] = new_image_url
                                # Also update id to indicate it's an external image
                                settings[bg_key]['id'] = ''
                            else:
                                settings[bg_key] = new_image_url
                            image_replacements += 1
                            print(f"Replaced background image in element {element_id} with {new_image_url}")
            
            # Process nested elements
            if 'elements' in element and isinstance(element['elements'], list):
                for child in element['elements']:
                    process_element(child)
    
    if isinstance(elementor_data, list):
        for element in elementor_data:
            process_element(element)
    else:
        process_element(elementor_data)
    
    print(f"Total image replacements: {image_replacements}")
    return elementor_data

def determine_image_context(element):
    """
    Determine the context of an image based on the element properties.
    This helps generate more relevant image search keywords.
    
    Args:
        element: The Elementor element containing the image
        
    Returns:
        A string describing the context of the image
    """
    element_type = element.get('widgetType', element.get('elType', ''))
    settings = element.get('settings', {})
    
    # Check for explicit title or heading that might indicate purpose
    title = settings.get('title', '')
    heading = settings.get('heading', '')
    content = settings.get('content', '')
    
    # Start with element type as base context
    context = element_type
    
    # Add more specific context based on content
    if title:
        if len(title) < 50:  # Only use short titles
            context = f"{title} {context}"
    elif heading:
        if len(heading) < 50:  # Only use short headings
            context = f"{heading} {context}"
    
    # Check for common section types
    lower_content = content.lower() if isinstance(content, str) else ''
    if any(term in lower_content for term in ['hero', 'banner', 'header']):
        context = f"hero section {context}"
    elif any(term in lower_content for term in ['about', 'company', 'team']):
        context = f"about section {context}"
    elif any(term in lower_content for term in ['service', 'offer', 'product']):
        context = f"service section {context}"
    elif any(term in lower_content for term in ['contact', 'reach', 'email', 'phone']):
        context = f"contact section {context}"
    
    # Check parent element for section context
    parent_id = element.get('parent', '')
    if parent_id and parent_id.startswith('section'):
        context = f"section {context}"
    
    return context

# Example usage
# replace_text_and_colors('input/gbptheme.WordPress.2024-11-13.xml', 'data/transformed_content2.json', 'output/modified_wordpress_export.xml')
