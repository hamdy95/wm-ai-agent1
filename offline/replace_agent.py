import json
import xml.etree.ElementTree as ET
import os
import re
import traceback
from typing import Dict, List, Any, Optional, Tuple, Union
import uuid
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime

class OfflineReplaceAgent:
    """Agent that replaces transformed content in the original theme"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get Supabase credentials
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        self.supabase: Client = create_client(supabase_url, supabase_key)
    
    def scan_background_colors(self, elementor_data):
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
                
                # Process nested elements
                if 'elements' in element and isinstance(element['elements'], list):
                    for child in element['elements']:
                        scan_element(child)
        
        if isinstance(elementor_data, list):
            for item in elementor_data:
                scan_element(item)
        else:
            scan_element(elementor_data)
        
        return bg_colors

    def process_elementor_data(self, elementor_data, color_map, white_bg_colors):
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
                                            if orig_color.lower() in value.lower():
                                                settings[setting_key] = value.replace(orig_color, color_map[orig_color])
                                # For non-background colors, replace normally
                                else:
                                    for orig_color in color_map:
                                        if orig_color.lower() in value.lower():
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

    def replace_text_and_colors(self, source_xml_path_or_id, transformations_json_path, output_xml_path):
        """Replace text and colors in the XML file with transformed content"""
        try:
            print(f"Starting transformation from {source_xml_path_or_id} using {transformations_json_path}")
            ET.register_namespace('wp', 'http://wordpress.org/export/1.2/')
            ET.register_namespace('excerpt', 'http://wordpress.org/export/1.2/excerpt/')
            ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
            ET.register_namespace('wfw', 'http://wellformedweb.org/CommentAPI/')
            ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
            
            # Parse XML
            try:
                tree = ET.parse(source_xml_path_or_id)
                root = tree.getroot()
                print(f"Successfully parsed XML from {source_xml_path_or_id}")
            except Exception as e:
                print(f"Error parsing XML: {str(e)}")
                traceback.print_exc()
                raise ValueError(f"Invalid XML file: {source_xml_path_or_id}")
            
            # Load transformations
            try:
                with open(transformations_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"Successfully loaded transformation data from {transformations_json_path}")
            except Exception as e:
                print(f"Error loading transformations: {str(e)}")
                traceback.print_exc()
                raise ValueError(f"Invalid transformations JSON: {transformations_json_path}")
            
            # Initialize transformation structures
            text_transformations = []
            color_map = {}
            
            # Check if the transformation data has the expected structure with text_transformations
            if "text_transformations" in data and isinstance(data["text_transformations"], list):
                # Old format with text_transformations key
                text_transformations = data["text_transformations"]
                print(f"Found {len(text_transformations)} text transformations in old format")
                
                # Check for color palette in old format
                if "color_palette" in data and "original_colors" in data["color_palette"] and "new_colors" in data["color_palette"]:
                    original_colors = data["color_palette"]["original_colors"]
                    new_colors = data["color_palette"]["new_colors"]
                    
                    # Create mapping
                    if len(original_colors) == len(new_colors):
                        color_map = dict(zip(original_colors, new_colors))
                        print(f"Found {len(color_map)} color mappings in old format")
                    else:
                        print(f"Warning: Color arrays length mismatch - original: {len(original_colors)}, new: {len(new_colors)}")
            
            # Check for the new format with texts and colors directly
            elif "texts" in data and isinstance(data["texts"], list):
                # New format - texts array contains original and transformed texts alternating
                texts_array = data["texts"]
                print(f"Found {len(texts_array)} items in texts array (new format)")
                
                # Convert to text_transformations format
                for i in range(0, len(texts_array), 2):
                    if i + 1 < len(texts_array):
                        text_transformations.append({
                            "original": texts_array[i],
                            "transformed": texts_array[i + 1]
                        })
                
                # Process colors in new format
                if "colors" in data and isinstance(data["colors"], list):
                    colors_array = data["colors"]
                    print(f"Found {len(colors_array)} items in colors array (new format)")
                    
                    # Convert to color mapping
                    for i in range(0, len(colors_array), 2):
                        if i + 1 < len(colors_array):
                            color_map[colors_array[i]] = colors_array[i + 1]
            
            # If we still don't have transformations, check if the data itself is in the right format
            if not text_transformations and isinstance(data, list) and len(data) >= 2:
                # Assuming the list directly contains [original, transformed, original, transformed, ...]
                for i in range(0, len(data), 2):
                    if i + 1 < len(data):
                        text_transformations.append({
                            "original": data[i],
                            "transformed": data[i + 1]
                        })
            
            print(f"Final transformation counts: {len(text_transformations)} text transformations and {len(color_map)} color mappings")
            
            if not text_transformations and not color_map:
                print("Warning: No usable transformations found in the data")
            
            # Store white background colors
            white_colors = {}
            for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
                if item.text and '[{' in item.text:
                    try:
                        elementor_data = json.loads(item.text)
                        page_colors = self.scan_background_colors(elementor_data)
                        white_colors.update(page_colors)
                    except json.JSONDecodeError:
                        continue
            
            print(f"Found {len(white_colors)} elements with white backgrounds to preserve")
            
            # Replace text in the XML
            replaced_count = 0
            for transformation in text_transformations:
                if "original" not in transformation or "transformed" not in transformation:
                    print(f"Warning: Invalid transformation format: {transformation}")
                    continue
                    
                original_text = transformation["original"]
                transformed_text = transformation["transformed"]
                
                if not original_text or not transformed_text:
                    continue
                
                for elem in root.iter():
                    if elem.text and original_text in elem.text:
                        elem.text = elem.text.replace(original_text, transformed_text)
                        replaced_count += 1
                    if elem.tail and original_text in elem.tail:
                        elem.tail = elem.tail.replace(original_text, transformed_text)
                        replaced_count += 1
                    if elem.attrib:
                        for attr_key, attr_value in elem.attrib.items():
                            if original_text in attr_value:
                                elem.attrib[attr_key] = attr_value.replace(original_text, transformed_text)
                                replaced_count += 1
            
            print(f"Replaced text in {replaced_count} places")
            
            # Process XML with preserved white backgrounds
            json_modified_count = 0
            for item in root.findall('.//wp:meta_value', {'wp': 'http://wordpress.org/export/1.2/'}):
                if item.text and '[{' in item.text:
                    try:
                        elementor_data = json.loads(item.text)
                        modified_data = self.process_elementor_data(elementor_data, color_map, white_colors)
                        item.text = json.dumps(modified_data)
                        json_modified_count += 1
                    except json.JSONDecodeError:
                        continue
            
            print(f"Modified colors in {json_modified_count} Elementor data blocks while preserving white backgrounds")
            
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_xml_path), exist_ok=True)
            
            # Write the modified XML to the output file
            tree.write(output_xml_path, encoding='utf-8', xml_declaration=True)
            print(f"Successfully wrote transformed XML to {output_xml_path}")
            
            return output_xml_path
            
        except Exception as e:
            print(f"Error in replace_text_and_colors: {str(e)}")
            traceback.print_exc()
            raise

def main():
    # Example usage
    agent = OfflineReplaceAgent()
    
    # Replace test
    xml_file = "input/theme.xml"  # Replace with your input XML path
    json_file = "transformed_content_c506a002-029a-4ce3-b0bc-3eefdd331c7a.json"  # Replace with your transformed content JSON
    output_file = "output/modified_theme.xml"  # Replace with your desired output path
    
    try:
        agent.replace_text_and_colors(xml_file, json_file, output_file)
        print(f"Theme replacement completed successfully!")
    except Exception as e:
        print(f"Theme replacement failed: {e}")

if __name__ == "__main__":
    main() 