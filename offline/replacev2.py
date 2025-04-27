import json
import xml.etree.ElementTree as ET
import os
import traceback
import re

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
                        color_value = str(settings[key]).lower()
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
    
    def process_element(element):
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
                            # For background-related keys, only replace if not white
                            if any(bg in setting_key.lower() for bg in ['background', 'bg_']):
                                value_lower = value.lower()
                                if value_lower not in ['#ffffff', '#fff', 'white']:
                                    for orig_color in color_map:
                                        if orig_color in value:
                                            settings[setting_key] = value.replace(orig_color, color_map[orig_color])
                            # For non-background colors, replace normally
                            else:
                                for orig_color in color_map:
                                    if orig_color in value:
                                        settings[setting_key] = value.replace(orig_color, color_map[orig_color])
            
            # Process nested elements
            if 'elements' in element and isinstance(element['elements'], list):
                for child in element['elements']:
                    process_element(child)
                    
    if isinstance(elementor_data, list):
        for item in elementor_data:
            process_element(item)
    else:
        process_element(elementor_data)
    
    return elementor_data

def extract_text(text_string):
    """Extract text from JSON string or object safely"""
    if not isinstance(text_string, str):
        return str(text_string)
        
    # If it's a JSON string with original/transformed fields
    if '"original"' in text_string or '"transformed"' in text_string:
        try:
            # Try to treat as JSON
            if text_string.startswith('"') and text_string.endswith('"'):
                # Remove outer quotes if present
                text_string = text_string[1:-1].replace('\\"', '"')
                
            if text_string.startswith('{') and text_string.endswith('}'):
                obj = json.loads(text_string)
                if isinstance(obj, dict):
                    if "original" in obj:
                        return obj["original"]
                    elif "transformed" in obj:
                        return obj["transformed"]
        except:
            # If JSON parsing fails, try regex
            match = re.search(r'"(original|transformed)":"([^"]+)"', text_string)
            if match:
                return match.group(2)
    
    # If all else fails, return the original string
    return text_string

def replace_text_and_colors(xml_file_path, json_file_path, output_file_path):
    print(f"\n=== Starting Theme Transformation ===")
    print(f"Input XML: {xml_file_path}")
    print(f"Transformation JSON: {json_file_path}")
    print(f"Output XML: {output_file_path}")
    
    # Register namespaces
    ET.register_namespace('wp', 'http://wordpress.org/export/1.2/')
    ET.register_namespace('excerpt', 'http://wordpress.org/export/1.2/excerpt/')
    ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
    ET.register_namespace('wfw', 'http://wellformedweb.org/CommentAPI/')
    ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
    
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    
    with open(json_file_path, 'r', encoding='utf-8') as json_file:
        data = json.load(json_file)
    
    # Get text transformations
    raw_transformations = data.get("text_transformations", [])
    print(f"Loaded {len(raw_transformations)} raw text transformations")
    
    # Extract actual text from potentially JSON-encoded strings
    text_transformations = []
    for item in raw_transformations:
        if isinstance(item, dict) and "original" in item and "transformed" in item:
            original = extract_text(item["original"])
            transformed = extract_text(item["transformed"])
            if original and transformed:
                text_transformations.append({"original": original, "transformed": transformed})
                print(f"Added transformation: '{original[:30]}...' → '{transformed[:30]}...'")
    
    # Get color mappings
    original_colors = data["color_palette"]["original_colors"]
    new_colors = data["color_palette"]["new_colors"]
    print(f"Loaded {len(original_colors)} original colors and {len(new_colors)} new colors")
    
    color_map = {}
    for i in range(min(len(original_colors), len(new_colors))):
        orig = original_colors[i]
        new = new_colors[i]
        
        # Handle potential JSON encoding in colors
        if isinstance(orig, str) and orig.startswith('{'):
            try:
                obj = json.loads(orig)
                if isinstance(obj, dict) and "from" in obj:
                    orig = obj["from"]
            except:
                # Try regex as fallback
                match = re.search(r'#[0-9a-fA-F]{3,6}', orig)
                if match:
                    orig = match.group(0)
        
        if isinstance(new, str) and new.startswith('{'):
            try:
                obj = json.loads(new)
                if isinstance(obj, dict) and "to" in obj:
                    new = obj["to"]
            except:
                # Try regex as fallback
                match = re.search(r'#[0-9a-fA-F]{3,6}', new)
                if match:
                    new = match.group(0)
        
        if orig and new:
            color_map[orig] = new
            print(f"Added color mapping: {orig} → {new}")

    # Replace text in the XML - using the original approach
    text_replacement_count = 0
    for transformation in text_transformations:
        original_text = transformation["original"]
        transformed_text = transformation["transformed"]
        
        for elem in root.iter():
            if elem.text and original_text in elem.text:
                elem.text = elem.text.replace(original_text, transformed_text)
                text_replacement_count += 1
                print(f"Replaced text: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
                
            if elem.tail and original_text in elem.tail:
                elem.tail = elem.tail.replace(original_text, transformed_text)
                text_replacement_count += 1
                print(f"Replaced tail: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
                
            if elem.attrib:
                for attr_key, attr_value in elem.attrib.items():
                    if original_text in attr_value:
                        elem.attrib[attr_key] = attr_value.replace(original_text, transformed_text)
                        text_replacement_count += 1
                        print(f"Replaced attribute: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
    
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
    color_replacement_count = 0
    for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
        if item.text and '[{' in item.text:
            try:
                elementor_data = json.loads(item.text)
                modified_data = process_elementor_data(elementor_data, color_map, white_colors)
                item.text = json.dumps(modified_data)
                color_replacement_count += 1
            except json.JSONDecodeError:
                continue
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    
    # Write the transformed XML
    tree.write(output_file_path, encoding='utf-8', xml_declaration=True)
    
    print(f"\n=== Transformation Complete ===")
    print(f"Text replacements: {text_replacement_count}")
    print(f"Color replacements: {color_replacement_count}")
    print(f"Output file: {output_file_path}")
    
    return output_file_path

def extract_actual_text(text_string):
    """Extract the actual text content from potentially JSON-encoded strings"""
    if not text_string:
        return ""
    
    # Try to parse as JSON if it looks like JSON
    if isinstance(text_string, str) and (text_string.startswith('{') or text_string.startswith('"{')):
        try:
            # Remove outer quotes if present
            if text_string.startswith('"') and text_string.endswith('"'):
                text_string = text_string[1:-1].replace('\\"', '"')
            
            # Parse as JSON
            parsed = json.loads(text_string)
            
            # Extract text from parsed object
            if isinstance(parsed, dict):
                if "original" in parsed:
                    return parsed["original"]
                elif "transformed" in parsed:
                    return parsed["transformed"]
                else:
                    return text_string
            else:
                return text_string
        except:
            # If JSON parsing fails, try regex extraction
            match = re.search(r'"(original|transformed)":"([^"]+)"', text_string)
            if match:
                return match.group(2)
            else:
                # If all else fails, return the original string
                return text_string
    else:
        return text_string

def replace_text_and_colors(xml_file_path, json_file_path, output_file_path):
    print(f"\n=== Starting Theme Transformation ===")
    print(f"Input XML: {xml_file_path}")
    print(f"Transformation JSON: {json_file_path}")
    print(f"Output XML: {output_file_path}")
    
    try:
        # Register all required namespaces
        ET.register_namespace('wp', 'http://wordpress.org/export/1.2/')
        ET.register_namespace('excerpt', 'http://wordpress.org/export/1.2/excerpt/')
        ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
        ET.register_namespace('wfw', 'http://wellformedweb.org/CommentAPI/')
        ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
        
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            data = json.load(json_file)
        
        # Process text transformations
        text_transformations = data.get("text_transformations", [])
        print(f"Processing {len(text_transformations)} text transformations")
        
        # Create a clean list of text transformations
        clean_transformations = []
        for transformation in text_transformations:
            original_raw = transformation.get("original", "")
            transformed_raw = transformation.get("transformed", "")
            
            # Extract actual text content
            original_text = extract_actual_text(original_raw)
            transformed_text = extract_actual_text(transformed_raw)
            
            if original_text and transformed_text and original_text != transformed_text:
                clean_transformations.append((original_text, transformed_text))
                print(f"Added transformation: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
        
        # Process color mappings
        original_colors = data["color_palette"]["original_colors"]
        new_colors = data["color_palette"]["new_colors"]
        
        # Create clean color mappings
        color_map = {}
        min_len = min(len(original_colors), len(new_colors))
        for i in range(min_len):
            orig_color = original_colors[i]
            new_color = new_colors[i]
            
            # Handle JSON strings in colors
            if isinstance(orig_color, str) and (orig_color.startswith('{') or orig_color.startswith('\"{')):
                try:
                    # Extract the actual color code
                    if orig_color.startswith('"') and orig_color.endswith('"'):
                        orig_color = orig_color[1:-1].replace('\\"', '"')
                    
                    parsed = json.loads(orig_color)
                    if isinstance(parsed, dict) and "from" in parsed:
                        orig_color = parsed["from"]
                    elif isinstance(parsed, dict) and "to" in parsed:
                        orig_color = parsed["to"]
                    else:
                        # Try to extract hex color
                        hex_colors = re.findall(r'#[0-9a-fA-F]{3,6}', orig_color)
                        if hex_colors:
                            orig_color = hex_colors[0]
                except:
                    hex_colors = re.findall(r'#[0-9a-fA-F]{3,6}', orig_color)
                    if hex_colors:
                        orig_color = hex_colors[0]
            
            if isinstance(new_color, str) and (new_color.startswith('{') or new_color.startswith('\"{')):
                try:
                    # Extract the actual color code
                    if new_color.startswith('"') and new_color.endswith('"'):
                        new_color = new_color[1:-1].replace('\\"', '"')
                    
                    parsed = json.loads(new_color)
                    if isinstance(parsed, dict) and "to" in parsed:
                        new_color = parsed["to"]
                    elif isinstance(parsed, dict) and "from" in parsed:
                        new_color = parsed["from"]
                    else:
                        # Try to extract hex color
                        hex_colors = re.findall(r'#[0-9a-fA-F]{3,6}', new_color)
                        if hex_colors:
                            new_color = hex_colors[0]
                except:
                    hex_colors = re.findall(r'#[0-9a-fA-F]{3,6}', new_color)
                    if hex_colors:
                        new_color = hex_colors[0]
            
            # Add to color map if valid hex color
            if orig_color and new_color and re.match(r'^#[0-9a-fA-F]{3,6}$', orig_color):
                color_map[orig_color] = new_color
                print(f"Added color mapping: {orig_color} → {new_color}")
        
        print(f"Processing {len(clean_transformations)} clean text transformations and {len(color_map)} color mappings")

        # Replace text in the XML
        text_replacement_count = 0
        for original_text, transformed_text in clean_transformations:
            for elem in root.iter():
                if elem.text and original_text in elem.text:
                    elem.text = elem.text.replace(original_text, transformed_text)
                    text_replacement_count += 1
                    print(f"Replaced in element text: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
                
                if elem.tail and original_text in elem.tail:
                    elem.tail = elem.tail.replace(original_text, transformed_text)
                    text_replacement_count += 1
                    print(f"Replaced in element tail: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
                
                if elem.attrib:
                    for attr_key, attr_value in elem.attrib.items():
                        if original_text in attr_value:
                            elem.attrib[attr_key] = attr_value.replace(original_text, transformed_text)
                            text_replacement_count += 1
                            print(f"Replaced in attribute {attr_key}: '{original_text[:30]}...' → '{transformed_text[:30]}...'")
        
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
        
        print(f"Found {len(white_colors)} elements with white backgrounds to preserve")
        
        # Process XML with preserved white backgrounds
        color_replacement_count = 0
        for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
            if item.text and '[{' in item.text:
                try:
                    elementor_data = json.loads(item.text)
                    modified_data, count = process_elementor_data(elementor_data, color_map, white_colors)
                    item.text = json.dumps(modified_data)
                    color_replacement_count += count
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Error processing colors: {e}")
        
        # Write the output file
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        tree.write(output_file_path, encoding='utf-8', xml_declaration=True)
        
        print(f"\n=== Transformation Complete ===")
        print(f"Text replacements: {text_replacement_count}")
        print(f"Color replacements: {color_replacement_count}")
        print(f"Output file: {output_file_path}")
        
        return output_file_path
    
    except Exception as e:
        print(f"ERROR: Failed to process theme: {e}")
        traceback.print_exc()
        raise 