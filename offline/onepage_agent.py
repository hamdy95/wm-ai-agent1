import os
import json
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Optional, Tuple, Union
import uuid
import random
from supabase import create_client, Client
from datetime import datetime
from dotenv import load_dotenv

# Import color utilities for better color generation
try:
    from color_utils import extract_color_from_description, generate_color_palette as generate_smart_palette, map_colors_to_elementor
    # Define a fallback for create_accessible_text_colors if it doesn't exist
    def create_accessible_text_colors(palette):
        # Simple fallback that returns black and white text colors
        return {
            'text_on_primary': (255, 255, 255),  # White text on primary
            'text_on_light': (0, 0, 0),          # Black text on light backgrounds
            'text_on_dark': (255, 255, 255)       # White text on dark backgrounds
        }
    print("Successfully imported color_utils with function adaptations.")
except ImportError:
    print("Warning: Could not import color_utils. Using fallback color method.")

class OnePageSiteGenerator:
    """Agent that creates one-page websites by selecting sections from the database"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get Supabase credentials
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Define section mapping
        self.section_mapping = {
            'main': ['main', 'main section', 'main content'],
            'hero': ['hero', 'banner', 'header'],
            'about': ['about', 'company', 'who we are', 'our story'],
            'services': ['services', 'what we do', 'offerings', 'solutions'],
            'features': ['features', 'benefits', 'advantages'],
            'portfolio': ['portfolio', 'work', 'projects', 'gallery', 'case study', 'showcase'],
            'team': ['team', 'members', 'staff', 'our people'],
            'testimonials': ['testimonials', 'reviews', 'what clients say'],
            'pricing': ['pricing', 'plans', 'packages', 'subscriptions'],
            'contact': ['contact', 'get in touch', 'reach us', 'location'],
            'faq': ['faq', 'questions', 'answers', 'help'],
            'cta': ['cta', 'call to action', 'sign up', 'join'],
            'clients': ['clients', 'partners', 'brands'],
            'footer': ['footer', 'bottom'],
            'map': ['map', 'google map', 'location', 'address', 'find us', 'directions', 'where we are']
        }

    def parse_user_query(self, query: str) -> List[str]:
        """Parse user query to identify required sections"""
        query = query.lower()
        requested_sections = []
        
        # Look for section keywords in the query
        for section_type, keywords in self.section_mapping.items():
            for keyword in keywords:
                if keyword in query:
                    requested_sections.append(section_type)
                    break
        
        # Check for specific requests like "I need 5 sections"
        num_sections_match = re.search(r'(\d+)\s+sections', query)
        if num_sections_match:
            num_sections = int(num_sections_match.group(1))
            if len(requested_sections) < num_sections:
                # Add more sections to meet the requested count
                available_sections = list(self.section_mapping.keys())
                # Remove already requested sections
                for section in requested_sections:
                    if section in available_sections:
                        available_sections.remove(section)
                
                # Randomly select additional sections
                additional_sections = random.sample(available_sections, 
                                                 min(num_sections - len(requested_sections), 
                                                     len(available_sections)))
                requested_sections.extend(additional_sections)
        
        # Make sure we have at least one section (main or hero)
        if not requested_sections:
            requested_sections.append('main')
        
        # Order sections in a logical way (main/hero first, contact/footer last)
        ordered_sections = []
        
        # Main always comes first if present
        if 'main' in requested_sections:
            ordered_sections.append('main')
            requested_sections.remove('main')
        # Otherwise hero comes first if present
        elif 'hero' in requested_sections:
            ordered_sections.append('hero')
            requested_sections.remove('hero')
        
        # Middle sections
        middle_sections = [s for s in requested_sections if s not in ['contact', 'cta', 'footer']]
        ordered_sections.extend(middle_sections)
        
        # CTA before contact
        if 'cta' in requested_sections:
            ordered_sections.append('cta')
        
        # Contact near the end
        if 'contact' in requested_sections:
            ordered_sections.append('contact')
        
        # Footer always last
        if 'footer' in requested_sections:
            ordered_sections.append('footer')
        
        return ordered_sections

    def fetch_sections(self, section_types: List[str]) -> Dict[str, Any]:
        """Fetch sections of the requested types from Supabase"""
        selected_sections = {}
        fallback_sections = {}
        missing_sections = []
        
        # First attempt - exact category match
        for section_type in section_types:
            # Query the database for sections of this type
            try:
                result = self.supabase.table('sections') \
                    .select('*') \
                    .eq('category', section_type) \
                    .execute()
                
                if result.data:
                    # Randomly select one section of this type
                    selected_section = random.choice(result.data)
                    selected_sections[section_type] = selected_section
                    print(f"Found section for type: {section_type}")
                else:
                    missing_sections.append(section_type)
                    print(f"No sections found for type: {section_type}")
            except Exception as e:
                missing_sections.append(section_type)
                print(f"Error fetching {section_type} sections: {e}")
        
        # Second attempt - for missing sections, try search in content or other fields
        if missing_sections:
            print(f"Searching for alternative sections for: {missing_sections}")
            
            # Get all available sections
            try:
                all_sections_result = self.supabase.table('sections').select('*').execute()
                
                if all_sections_result.data:
                    all_sections = all_sections_result.data
                    
                    # For each missing section
                    for section_type in missing_sections:
                        matches = []
                        # Look for sections that might match based on content
                        for section in all_sections:
                            # Check if section type appears in content
                            section_content = section.get('content', '')
                            if isinstance(section_content, str):
                                # Try to parse section content if it's a JSON string
                                try:
                                    content_data = json.loads(section_content)
                                    # Look for sections that have relevant keywords in their content
                                    if any(keyword in json.dumps(content_data).lower() for keyword in self.section_mapping.get(section_type, [])):
                                        matches.append(section)
                                except:
                                    # If not JSON, check the content as string
                                    if any(keyword in section_content.lower() for keyword in self.section_mapping.get(section_type, [])):
                                        matches.append(section)
                            
                            # Also check title, description, or other fields
                            for field in ['title', 'description', 'name', 'type']:
                                if field in section and section[field]:
                                    if any(keyword in str(section[field]).lower() for keyword in self.section_mapping.get(section_type, [])):
                                        matches.append(section)
                                        break
                        
                        # If we found any matches, randomly select one
                        if matches:
                            fallback_section = random.choice(matches)
                            fallback_sections[section_type] = fallback_section
                            print(f"Found alternative section for {section_type} with content match")
                        else:
                            # No match found for this section type, try to find a generic one
                            generic_types = ['content', 'section', 'block', 'element', 'widget']
                            generic_matches = []
                            
                            for section in all_sections:
                                for g_type in generic_types:
                                    if g_type in json.dumps(section).lower():
                                        generic_matches.append(section)
                                        break
                            
                            if generic_matches:
                                fallback_section = random.choice(generic_matches)
                                fallback_sections[section_type] = fallback_section
                                print(f"Used generic section for {section_type}")
            except Exception as e:
                print(f"Error finding alternative sections: {e}")
        
        # Merge selected and fallback sections
        selected_sections.update(fallback_sections)
        
        print(f"Successfully selected {len(selected_sections)} sections out of {len(section_types)} requested")
        return selected_sections

    def create_base_template(self) -> ET.Element:
        """Create a base WordPress export template with proper WXR version"""
        # Register namespaces for prefixes
        ET.register_namespace('excerpt', 'http://wordpress.org/export/1.2/excerpt/')
        ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
        ET.register_namespace('wfw', 'http://wellformedweb.org/CommentAPI/')
        ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
        ET.register_namespace('wp', 'http://wordpress.org/export/1.2/')
        
        # Create the root element with version only
        rss = ET.Element('rss', {'version': '2.0'})
        
        # Create the channel element
        channel = ET.SubElement(rss, 'channel')
        
        # Add basic site information
        title = ET.SubElement(channel, 'title')
        title.text = 'Generated One-Page Site'
        
        link = ET.SubElement(channel, 'link')
        link.text = 'https://example.com'
        
        description = ET.SubElement(channel, 'description')
        description.text = 'A one-page website generated from selected sections'
        
        # Add generator info
        generator = ET.SubElement(channel, 'generator')
        generator.text = 'WordPress One-Page Site Generator 1.0'
        
        # Add language
        language = ET.SubElement(channel, 'language')
        language.text = 'en-US'
        
        # Add wxr_version - this is critical for WordPress to recognize the file
        wxr_version = ET.SubElement(channel, '{http://wordpress.org/export/1.2/}wxr_version')
        wxr_version.text = '1.2'
        
        # Add wp:base_site_url
        base_site_url = ET.SubElement(channel, '{http://wordpress.org/export/1.2/}base_site_url')
        base_site_url.text = 'https://example.com'
        
        # Add wp:base_blog_url
        base_blog_url = ET.SubElement(channel, '{http://wordpress.org/export/1.2/}base_blog_url')
        base_blog_url.text = 'https://example.com'
        
        return rss

    def _fix_white_text_colors(self, elementor_data, safe_color='#222222'):
        """Recursively replace any white text color values with a safe default color."""
        def fix_element(element):
            if isinstance(element, dict):
                # Fix text color in settings
                settings = element.get('settings', {})
                if isinstance(settings, dict):
                    for key, value in settings.items():
                        if isinstance(value, str) and 'color' in key.lower():
                            val = value.strip().lower()
                            if val in ['#fff', '#ffffff', 'white']:
                                settings[key] = safe_color
                # Recurse into children
                if 'elements' in element and isinstance(element['elements'], list):
                    for child in element['elements']:
                        fix_element(child)
            elif isinstance(element, list):
                for item in element:
                    fix_element(item)
        fix_element(elementor_data)
        return elementor_data
        
    def _apply_color_palette(self, elementor_data, style_description):
        """Apply a color palette to the elementor data based on the style description."""
        # Check if we have the color_utils module available
        if 'extract_color_from_description' not in globals():
            print("Color utilities not available, skipping color palette application")
            return elementor_data
            
        try:
            # Extract primary color from style description
            primary_color = extract_color_from_description(style_description)
            print(f"Extracted primary color: {primary_color} from '{style_description}'")
            
            # Generate a color palette based on the primary color
            palette = generate_smart_palette(primary_color)
            print(f"Generated smart color palette with {len(palette)} colors")
            
            # Generate text colors for accessibility
            text_colors = create_accessible_text_colors(palette)
            print(f"Generated accessible text colors for the palette")
            
            # Map the palette to Elementor properties
            elementor_color_map = map_colors_to_elementor(palette, text_colors)
            print(f"Mapped {len(elementor_color_map)} Elementor properties to colors")
            
            # Apply the colors to the Elementor data
            def apply_colors(element):
                if isinstance(element, dict):
                    # Apply colors to settings
                    settings = element.get('settings', {})
                    if isinstance(settings, dict):
                        for key, value in list(settings.items()):
                            # If this is a color property and we have a mapping for it
                            if key in elementor_color_map:
                                # Don't replace white backgrounds
                                if 'background' in key.lower() and isinstance(value, str):
                                    val = value.strip().lower()
                                    if val in ['#fff', '#ffffff', 'white']:
                                        continue
                                # Apply the mapped color
                                settings[key] = elementor_color_map[key]
                            # For other color properties, try to match by type
                            elif isinstance(value, str) and re.match(r'^#[0-9A-Fa-f]{3,6}$', value):
                                # Apply color based on property name patterns
                                if 'background' in key.lower() and not any(x in key.lower() for x in ['hover', 'overlay']):
                                    # Skip white backgrounds
                                    if value.lower() not in ['#fff', '#ffffff']:
                                        settings[key] = elementor_color_map.get('background_color', value)
                                elif 'title' in key.lower() or 'heading' in key.lower():
                                    settings[key] = elementor_color_map.get('title_color', value)
                                elif any(x in key.lower() for x in ['text', 'content', 'description']):
                                    settings[key] = elementor_color_map.get('description_color', value)
                                elif 'button' in key.lower() and 'background' in key.lower():
                                    settings[key] = elementor_color_map.get('button_background_color', value)
                                elif 'button' in key.lower() and 'text' in key.lower():
                                    settings[key] = elementor_color_map.get('button_text_color', value)
                                elif 'icon' in key.lower():
                                    settings[key] = elementor_color_map.get('icon_color', value)
                                elif 'border' in key.lower():
                                    settings[key] = elementor_color_map.get('border_color', value)
                    
                    # Recurse into children
                    if 'elements' in element and isinstance(element['elements'], list):
                        for child in element['elements']:
                            apply_colors(child)
                elif isinstance(element, list):
                    for item in element:
                        apply_colors(item)
            
            # Apply colors to the Elementor data
            apply_colors(elementor_data)
            print("Applied color palette to Elementor data")
            
            return elementor_data
        except Exception as e:
            print(f"Error applying color palette: {e}")
            import traceback
            traceback.print_exc()
            return elementor_data

    def _apply_style_to_text(self, text: str, style_description: Optional[str]) -> str:
        """Transform text to reflect the style description (simple prompt-based rewrite)."""
        if not style_description or not text or not isinstance(text, str):
            return text
        # Simple heuristic: append a style hint, or inject style words if not present
        # (For production, use an LLM or more advanced NLP)
        style_hint = f" ({style_description})"
        if style_description.lower() not in text.lower():
            # Only append if not already present
            return text.strip() + style_hint
        return text

    def _transform_section_texts(self, section_content: dict, style_description: Optional[str]) -> dict:
        """Recursively apply style transformation to all text fields in section content."""
        if isinstance(section_content, dict):
            for k, v in section_content.items():
                if isinstance(v, str):
                    # Heuristic: likely text fields
                    if k in ['title', 'heading', 'subtitle', 'description', 'text', 'content', 'label', 'button_text', 'cta_text', 'excerpt']:
                        section_content[k] = self._apply_style_to_text(v, style_description)
                elif isinstance(v, (dict, list)):
                    section_content[k] = self._transform_section_texts(v, style_description)
        elif isinstance(section_content, list):
            for i, v in enumerate(section_content):
                section_content[i] = self._transform_section_texts(v, style_description)
        return section_content

    def create_one_page_site(self, user_query: str, output_path: str, style_description: Optional[str] = None) -> str:
        """Create a one-page WordPress site from the user query, applying style-aware text transformation."""
        # Parse the user query to get requested sections
        section_types = self.parse_user_query(user_query)
        print(f"Identified section types: {section_types}")
        
        # Fetch sections from Supabase
        selected_sections = self.fetch_sections(section_types)
        print(f"Selected {len(selected_sections)} sections")
        
        # Create a base template with proper namespace registration
        rss = self.create_base_template()
        channel = rss.find('channel')
        
        # Create a single page item
        item = ET.SubElement(channel, 'item')
        
        # Add basic page information
        title = ET.SubElement(item, 'title')
        title.text = 'Home'
        
        link = ET.SubElement(item, 'link')
        link.text = 'https://example.com/'
        
        pubDate = ET.SubElement(item, 'pubDate')
        pubDate.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        creator = ET.SubElement(item, '{http://purl.org/dc/elements/1.1/}creator')
        creator.text = 'admin'
        
        guid = ET.SubElement(item, 'guid')
        guid.set('isPermaLink', 'false')
        guid.text = f'https://example.com/?page_id=1'
        
        description = ET.SubElement(item, 'description')
        description.text = ''
        
        content = ET.SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded')
        content.text = ''
        
        excerpt = ET.SubElement(item, '{http://wordpress.org/export/1.2/excerpt/}encoded')
        excerpt.text = ''
        
        post_id = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_id')
        post_id.text = '1'
        
        post_date = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date')
        post_date.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        post_date_gmt = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date_gmt')
        post_date_gmt.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        comment_status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}comment_status')
        comment_status.text = 'closed'
        
        ping_status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}ping_status')
        ping_status.text = 'closed'
        
        post_name = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_name')
        post_name.text = 'home'
        
        status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}status')
        status.text = 'publish'
        
        post_parent = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_parent')
        post_parent.text = '0'
        
        menu_order = ET.SubElement(item, '{http://wordpress.org/export/1.2/}menu_order')
        menu_order.text = '0'
        
        post_type = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_type')
        post_type.text = 'page'
        
        post_password = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_password')
        post_password.text = ''
        
        is_sticky = ET.SubElement(item, '{http://wordpress.org/export/1.2/}is_sticky')
        is_sticky.text = '0'
        
        # Add page template meta
        meta_template = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_template, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_wp_page_template'
        meta_value = ET.SubElement(meta_template, '{http://wordpress.org/export/1.2/}meta_value')
        meta_value.text = 'elementor_header_footer'
        
        # Combine Elementor data from all sections
        elementor_data = []
        for section_type, section in selected_sections.items():
            # Parse the content JSON
            try:
                section_content = json.loads(section['content'])
                if 'section_data' in section_content:
                    # Apply style transformation to text fields
                    if style_description:
                        section_content['section_data'] = self._transform_section_texts(section_content['section_data'], style_description)
                    
                    # Apply color palette based on style description
                    if style_description:
                        # First apply our new color palette
                        section_content['section_data'] = self._apply_color_palette(section_content['section_data'], style_description)
                    
                    # Fix white text colors before adding (as a fallback)
                    fixed_section = self._fix_white_text_colors(section_content['section_data'])
                    elementor_data.append(fixed_section)
            except Exception as e:
                print(f"Error parsing section content for {section_type}: {e}")
        
        # Add Elementor data meta
        meta_elementor = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_elementor_data'
        meta_value = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_value')
        
        # Fix JSON serialization to prevent double escaping
        # Use plain text instead of CDATA to avoid recursion issues
        meta_value.text = json.dumps(elementor_data, ensure_ascii=False, separators=(',', ':'))
        
        # Add Elementor edit mode meta
        meta_edit_mode = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_edit_mode, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_elementor_edit_mode'
        meta_value = ET.SubElement(meta_edit_mode, '{http://wordpress.org/export/1.2/}meta_value')
        meta_value.text = 'builder'
        
        # Create the output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create the ElementTree and properly write it to file
        tree = ET.ElementTree(rss)
        
        # Use a properly formatted XML declaration with correct encoding
        with open(output_path, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            # Use xml_declaration=False since we manually added the declaration above
            tree.write(f, encoding='UTF-8', xml_declaration=False)
        
        # Validate the XML before returning
        try:
            ET.parse(output_path)
            print(f"One-page site generated at: {output_path}")
            return output_path
        except ET.ParseError as e:
            os.remove(output_path)
            raise ValueError(f"Generated XML is invalid: {str(e)}")
        except Exception as e:
            os.remove(output_path)
            raise ValueError(f"Error validating generated XML: {str(e)}")

def main():
    # Example usage
    generator = OnePageSiteGenerator()
    
    # Generate one-page site from query
    user_query = "I need a website with hero section, about us, services, and contact form"
    output_path = "output/one_page_site.xml"
    
    try:
        generator.create_one_page_site(user_query, output_path)
        print(f"One-page site generation successful!")
    except Exception as e:
        print(f"One-page site generation failed: {e}")

if __name__ == "__main__":
    main()
