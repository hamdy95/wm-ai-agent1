import json
import xml.etree.ElementTree as ET
import os
import re

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
    """Scan and store white background colors only"""
    bg_colors = {}
    
    def scan_element(element):
        if isinstance(element, dict):
            if 'id' in element and 'settings' in element:
                element_id = element['id']
                settings = element['settings']
                
                # Background color keys to check
                bg_keys = [
                    'background_color',
                    'background_overlay_color',
                    '_background_color',
                    '_background_background',
                    'background_overlay_background'
                ]
                
                # Store only white background colors
                for key in bg_keys:
                    if key in settings and settings[key]:
                        # Check if the color is white (case insensitive)
                        color_value = settings[key].lower()
                        if color_value in ['#ffffff', '#fff', 'white']:
                            if element_id not in bg_colors:
                                bg_colors[element_id] = {}
                            bg_colors[element_id][key] = settings[key]
    
    if isinstance(elementor_data, list):
        for item in elementor_data:
            scan_element(item)
    else:
        scan_element(elementor_data)
    
    return bg_colors

def process_elementor_data(elementor_data, color_map, white_bg_colors):
    """Process colors while preserving white backgrounds"""
    replaced_count = 0
    
    def process_element(element):
        nonlocal replaced_count
        if isinstance(element, dict):
            if 'settings' in element and 'id' in element:
                settings = element['settings']
                element_id = element['id']
                
                # Restore white background colors
                if element_id in white_bg_colors:
                    for key, value in white_bg_colors[element_id].items():
                        settings[key] = value
                
                # Process all other colors including non-white backgrounds
                if isinstance(settings, dict):
                    for setting_key in list(settings.keys()):
                        value = settings[setting_key]
                        if isinstance(value, str):
                            # Check if the value looks like a color code
                            if re.match(r'^#[0-9A-Fa-f]{3,6}$', value) or value.lower() in ['white', 'black', 'red', 'blue', 'green', 'yellow']:
                                # For background-related keys, only replace if not white
                                if any(bg in setting_key.lower() for bg in ['background', 'bg_']):
                                    value_lower = value.lower()
                                    if value_lower not in ['#ffffff', '#fff', 'white']:
                                        value_upper = value.upper()
                                        if value_upper in color_map:
                                            settings[setting_key] = color_map[value_upper]
                                            replaced_count += 1
                                            print(f"Replaced color: {value_upper} -> {color_map[value_upper]} in {setting_key}")
                                # For non-background colors, replace normally
                                else:
                                    value_upper = value.upper()
                                    if value_upper in color_map:
                                        settings[setting_key] = color_map[value_upper]
                                        replaced_count += 1
                                        print(f"Replaced color: {value_upper} -> {color_map[value_upper]} in {setting_key}")
            
            # Process nested elements
            if 'elements' in element and isinstance(element['elements'], list):
                for child in element['elements']:
                    process_element(child)
                    
    if isinstance(elementor_data, list):
        for item in elementor_data:
            process_element(item)
    else:
        process_element(elementor_data)
    
    print(f"Total color replacements in Elementor data: {replaced_count}")
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

def replace_text_and_colors(xml_file_path, json_file_path, output_file_path, verbose_debug=True):
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
            
            print(f"Created color map from color_palette with {len(color_map)} colors")
    
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
        for elem in root.iter():
            if elem.text and original_text in elem.text:
                elem.text = elem.text.replace(original_text, transformed_text)
                text_replaced_count += 1
                print(f"Replaced text: '{original_text[:30]}...' -> '{transformed_text[:30]}...'")
            
            if elem.tail and original_text in elem.tail:
                elem.tail = elem.tail.replace(original_text, transformed_text)
                text_replaced_count += 1
            
            if elem.attrib:
                for attr_key, attr_value in elem.attrib.items():
                    if original_text in attr_value:
                        elem.attrib[attr_key] = attr_value.replace(original_text, transformed_text)
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
    
    # Process XML with preserved white backgrounds
    elementor_text_replaced = 0
    for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
        if item.text and '[{' in item.text:
            try:
                elementor_data = json.loads(item.text)
                
                # Replace text in Elementor data
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
                                                    settings[key] = value.replace(original_text, transformed_text)
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
                    modified_data = process_elementor_data(elementor_data, color_map, white_colors)
                    item.text = json.dumps(modified_data)
                    color_replaced_count += 1
            except json.JSONDecodeError as e:
                print(f"Error decoding Elementor data: {e}")
                continue
            except Exception as e:
                print(f"Error processing Elementor data: {str(e)}")
                continue
    
    print(f"Replaced {elementor_text_replaced} text occurrences in Elementor data")
    print(f"Processed {color_replaced_count} Elementor sections for color replacements")
    
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    tree.write(output_file_path, encoding='utf-8', xml_declaration=True)
    print(f"Wrote modified XML to {output_file_path}")

# Example usage
# replace_text_and_colors('input/gbptheme.WordPress.2024-11-13.xml', 'data/transformed_content2.json', 'output/modified_wordpress_export.xml')




