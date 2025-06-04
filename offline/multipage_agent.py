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

class MultiPageSiteGenerator:
    """Agent that creates multi-page websites by selecting pages from the database"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get Supabase credentials
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Define page mapping
        self.page_mapping = {
            'home': ['home', 'homepage', 'main', 'index', 'landing'],
            'about': ['about', 'about us', 'company', 'who we are', 'our story'],
            'services': ['services', 'what we do', 'offerings', 'solutions', 'our services'],
            'portfolio': ['portfolio', 'work', 'projects', 'gallery', 'our work', 'case studies'],
            'contact': ['contact', 'get in touch', 'reach us', 'contact us', 'location'],
            'blog': ['blog', 'news', 'articles', 'posts'],
            'team': ['team', 'our team', 'members', 'staff', 'our people'],
            'testimonials': ['testimonials', 'reviews', 'what clients say'],
            'pricing': ['pricing', 'plans', 'packages', 'subscriptions'],
            'faq': ['faq', 'questions', 'answers', 'help', 'support'],
            'products': ['products', 'shop', 'store', 'merchandise']
        }
        
        # Define primary menu items with order
        self.primary_pages = ['home', 'about', 'services', 'portfolio', 'blog', 'contact']

    def parse_user_query(self, query: str) -> List[str]:
        """Parse user query to identify required pages"""
        query = query.lower()
        requested_pages = []
        
        # Look for page keywords in the query
        for page_type, keywords in self.page_mapping.items():
            for keyword in keywords:
                if keyword in query:
                    if page_type not in requested_pages:
                        requested_pages.append(page_type)
                    break
        
        # Check for specific requests like "I need 5 pages"
        num_pages_match = re.search(r'(\d+)\s+pages', query)
        if num_pages_match:
            num_pages = int(num_pages_match.group(1))
            if len(requested_pages) < num_pages:
                # Add more pages to meet the requested count
                available_pages = list(self.page_mapping.keys())
                # Remove already requested pages
                for page in requested_pages:
                    if page in available_pages:
                        available_pages.remove(page)
                
                # Prioritize primary pages first
                primary_candidates = [p for p in self.primary_pages if p in available_pages]
                secondary_candidates = [p for p in available_pages if p not in self.primary_pages]
                
                # Calculate how many more pages we need
                pages_needed = num_pages - len(requested_pages)
                
                # Select from primary pages first
                primary_to_add = min(pages_needed, len(primary_candidates))
                if primary_to_add > 0:
                    additional_primary = random.sample(primary_candidates, primary_to_add)
                    requested_pages.extend(additional_primary)
                    pages_needed -= primary_to_add
                
                # Then from secondary pages if needed
                if pages_needed > 0 and secondary_candidates:
                    additional_secondary = random.sample(secondary_candidates, 
                                                     min(pages_needed, len(secondary_candidates)))
                    requested_pages.extend(additional_secondary)
        
        # Make sure we have at least a home page
        if not requested_pages or 'home' not in requested_pages:
            requested_pages.insert(0, 'home')
        
        # Order pages in a logical way (home first, contact typically last)
        ordered_pages = []
        
        # Order by the primary pages list
        for page in self.primary_pages:
            if page in requested_pages:
                ordered_pages.append(page)
                requested_pages.remove(page)
        
        # Add any remaining pages
        ordered_pages.extend(requested_pages)
            
        return ordered_pages

    def fetch_pages(self, page_types: List[str]) -> Dict[str, Any]:
        """Fetch pages of the requested types from Supabase"""
        selected_pages = {}
        fallback_pages = {}
        missing_pages = []
        
        # First attempt - exact category match
        for page_type in page_types:
            # Query the database for pages of this type
            try:
                result = self.supabase.table('pages') \
                    .select('*') \
                    .eq('category', page_type) \
                    .execute()
                
                if result.data:
                    # Randomly select one page of this type
                    selected_page = random.choice(result.data)
                    selected_pages[page_type] = selected_page
                    print(f"Found page for type: {page_type}")
                else:
                    missing_pages.append(page_type)
                    print(f"No pages found for type: {page_type}")
            except Exception as e:
                missing_pages.append(page_type)
                print(f"Error fetching {page_type} pages: {e}")
        
        # Second attempt - for missing pages, try search in content or other fields
        if missing_pages:
            print(f"Searching for alternative pages for: {missing_pages}")
            
            # Get all available pages
            try:
                all_pages_result = self.supabase.table('pages').select('*').execute()
                
                if all_pages_result.data:
                    all_pages = all_pages_result.data
                    
                    # For each missing page
                    for page_type in missing_pages:
                        matches = []
                        # Look for pages that might match based on content
                        for page in all_pages:
                            # Check if page type appears in content
                            page_content = page.get('content', '')
                            if isinstance(page_content, str):
                                # Try to parse page content if it's a JSON string
                                try:
                                    content_data = json.loads(page_content)
                                    # Look for pages that have relevant keywords in their content
                                    if any(keyword in json.dumps(content_data).lower() for keyword in self.page_mapping.get(page_type, [])):
                                        matches.append(page)
                                except:
                                    # If not JSON, check the content as string
                                    if any(keyword in page_content.lower() for keyword in self.page_mapping.get(page_type, [])):
                                        matches.append(page)
                            
                            # Also check title, description, or other fields
                            for field in ['title', 'description', 'name', 'type']:
                                if field in page and page[field]:
                                    if any(keyword in str(page[field]).lower() for keyword in self.page_mapping.get(page_type, [])):
                                        matches.append(page)
                                        break
                        
                        # If we found any matches, randomly select one
                        if matches:
                            fallback_page = random.choice(matches)
                            fallback_pages[page_type] = fallback_page
                            print(f"Found alternative page for {page_type} with content match")
                        else:
                            # No match found for this page type, try to find a generic one
                            generic_types = ['content', 'page', 'block', 'element', 'widget']
                            generic_matches = []
                            
                            for page in all_pages:
                                for g_type in generic_types:
                                    if g_type in json.dumps(page).lower():
                                        generic_matches.append(page)
                                        break
                            
                            if generic_matches:
                                fallback_page = random.choice(generic_matches)
                                fallback_pages[page_type] = fallback_page
                                print(f"Used generic page for {page_type}")
            except Exception as e:
                print(f"Error finding alternative pages: {e}")
        
        # Merge selected and fallback pages
        selected_pages.update(fallback_pages)
        
        print(f"Successfully selected {len(selected_pages)} pages out of {len(page_types)} requested")
        return selected_pages

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
        title.text = 'Generated Multi-Page Site'
        
        link = ET.SubElement(channel, 'link')
        link.text = 'https://example.com'
        
        description = ET.SubElement(channel, 'description')
        description.text = 'A multi-page website generated from selected pages'
        
        # Add generator info
        generator = ET.SubElement(channel, 'generator')
        generator.text = 'WordPress Multi-Page Site Generator 1.0'
        
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

    def add_page_to_template(self, channel: ET.Element, page_type: str, page_data: Dict[str, Any], page_id: int, style_description: str = None) -> None:
        """Add a page to the XML template"""
        # Create page item
        item = ET.SubElement(channel, 'item')
        
        # Add basic page information
        title = ET.SubElement(item, 'title')
        title.text = page_data.get('title', page_type.capitalize())
        
        link = ET.SubElement(item, 'link')
        link.text = f'https://example.com/{page_type}/'
        
        pubDate = ET.SubElement(item, 'pubDate')
        pubDate.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        creator = ET.SubElement(item, '{http://purl.org/dc/elements/1.1/}creator')
        creator.text = 'admin'
        
        guid = ET.SubElement(item, 'guid')
        guid.set('isPermaLink', 'false')
        guid.text = f'https://example.com/?page_id={page_id}'
        
        description = ET.SubElement(item, 'description')
        description.text = ''
        
        content = ET.SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded')
        content.text = page_data.get('content', '')
        
        excerpt = ET.SubElement(item, '{http://wordpress.org/export/1.2/excerpt/}encoded')
        excerpt.text = ''
        
        post_id = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_id')
        post_id.text = str(page_id)
        
        post_date = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date')
        post_date.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        post_date_gmt = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date_gmt')
        post_date_gmt.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        comment_status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}comment_status')
        comment_status.text = 'closed'
        
        ping_status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}ping_status')
        ping_status.text = 'closed'
        
        post_name = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_name')
        post_name.text = page_type
        
        status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}status')
        status.text = 'publish'
        
        post_parent = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_parent')
        post_parent.text = '0'
        
        menu_order = ET.SubElement(item, '{http://wordpress.org/export/1.2/}menu_order')
        # Order pages according to their position
        if page_type == 'home':
            menu_order.text = '0'
        else:
            menu_order.text = str(self.primary_pages.index(page_type) if page_type in self.primary_pages else 99)
        
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
        
        # Add Elementor data if available
        elementor_data = page_data.get('elementor_data')
        if elementor_data:
            # If we have style_description and elementor_data is a string that looks like JSON
            if style_description and isinstance(elementor_data, str) and elementor_data.strip().startswith('[{'):
                try:
                    # Parse the elementor data
                    parsed_data = json.loads(elementor_data)
                    
                    # Apply our color palette
                    modified_data = self._apply_color_palette(parsed_data, style_description)
                    
                    # Convert back to string
                    elementor_data = json.dumps(modified_data)
                    print(f"Applied color palette to page {page_type}")
                except Exception as e:
                    print(f"Error applying color palette to page {page_type}: {e}")
            
            meta_elementor = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
            meta_key = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_key')
            meta_key.text = '_elementor_data'
            meta_value = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_value')
            meta_value.text = elementor_data
            
            # Add Elementor edit mode meta
            meta_edit_mode = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
            meta_key = ET.SubElement(meta_edit_mode, '{http://wordpress.org/export/1.2/}meta_key')
            meta_key.text = '_elementor_edit_mode'
            meta_value = ET.SubElement(meta_edit_mode, '{http://wordpress.org/export/1.2/}meta_value')
            meta_value.text = 'builder'

    def create_menu_item(self, channel: ET.Element, title: str, url: str, item_id: int, menu_order: int) -> None:
        """Add a menu item to the XML template"""
        # Create menu item
        item = ET.SubElement(channel, 'item')
        
        # Basic menu item info
        title_elem = ET.SubElement(item, 'title')
        title_elem.text = title
        
        link = ET.SubElement(item, 'link')
        link.text = url
        
        pubDate = ET.SubElement(item, 'pubDate')
        pubDate.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        creator = ET.SubElement(item, '{http://purl.org/dc/elements/1.1/}creator')
        creator.text = 'admin'
        
        guid = ET.SubElement(item, 'guid')
        guid.set('isPermaLink', 'false')
        guid.text = f'https://example.com/?p={item_id}'
        
        description = ET.SubElement(item, 'description')
        description.text = ''
        
        content = ET.SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded')
        content.text = ''
        
        excerpt = ET.SubElement(item, '{http://wordpress.org/export/1.2/excerpt/}encoded')
        excerpt.text = ''
        
        post_id = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_id')
        post_id.text = str(item_id)
        
        post_date = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date')
        post_date.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        post_date_gmt = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date_gmt')
        post_date_gmt.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        post_name = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_name')
        post_name.text = f'menu-item-{item_id}'
        
        status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}status')
        status.text = 'publish'
        
        post_type = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_type')
        post_type.text = 'nav_menu_item'
        
        # Menu item specific metadata
        meta_menu_item = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_menu_item, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_menu_item_type'
        meta_value = ET.SubElement(meta_menu_item, '{http://wordpress.org/export/1.2/}meta_value')
        meta_value.text = 'custom'
        
        meta_url = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_url, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_menu_item_url'
        meta_value = ET.SubElement(meta_url, '{http://wordpress.org/export/1.2/}meta_value')
        meta_value.text = url
        
        meta_title = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_title, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_menu_item_title'
        meta_value = ET.SubElement(meta_title, '{http://wordpress.org/export/1.2/}meta_value')
        meta_value.text = title
        
        meta_order = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
        meta_key = ET.SubElement(meta_order, '{http://wordpress.org/export/1.2/}meta_key')
        meta_key.text = '_menu_item_menu_order'
        meta_value = ET.SubElement(meta_order, '{http://wordpress.org/export/1.2/}meta_value')
        meta_value.text = str(menu_order)

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

    def create_multi_page_site(self, user_query: str, output_path: str, style_description: str = None) -> str:
        """Create a multi-page WordPress site from the user query"""
        # Parse the user query to get requested pages
        page_types = self.parse_user_query(user_query)
        print(f"Identified page types: {page_types}")
        
        # Fetch pages from Supabase
        selected_pages = self.fetch_pages(page_types)
        print(f"Selected {len(selected_pages)} pages")
        
        # Create a base template
        rss = self.create_base_template()
        channel = rss.find('channel')
        
        # Add each page to the template
        page_id = 1
        for page_type in page_types:
            if page_type in selected_pages:
                self.add_page_to_template(channel, page_type, selected_pages[page_type], page_id, style_description)
                page_id += 1
        
        # Create menu items for navigation
        menu_id = 100  # Start menu items at ID 100
        for idx, page_type in enumerate(page_types):
            if page_type in selected_pages:
                self.create_menu_item(
                    channel,
                    selected_pages[page_type].get('title', page_type.capitalize()),
                    f'https://example.com/{page_type}/',
                    menu_id + idx,
                    idx
                )
        
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
            print(f"Multi-page site generated at: {output_path}")
            return output_path
        except ET.ParseError as e:
            os.remove(output_path)
            raise ValueError(f"Generated XML is invalid: {str(e)}")
        except Exception as e:
            os.remove(output_path)
            raise ValueError(f"Error validating generated XML: {str(e)}")

def main():
    # Example usage
    generator = MultiPageSiteGenerator()
    
    # Generate multi-page site from query
    user_query = "I need a website with 5 pages: home, about us, services, portfolio and contact form"
    output_path = "output/multi_page_site.xml"
    
    try:
        generator.create_multi_page_site(user_query, output_path)
        print(f"Multi-page site generation successful!")
    except Exception as e:
        print(f"Multi-page site generation failed: {e}")

if __name__ == "__main__":
    main()
