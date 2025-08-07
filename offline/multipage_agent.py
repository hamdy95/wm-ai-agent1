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
from offline.color_utils import generate_color_palette_with_gpt4o

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
        """Parse user query to identify required pages - only return exactly what was requested"""
        query = query.lower()
        requested_pages = []
        
        # Define exact page name mappings for better matching
        page_name_mappings = {
            'home': ['home', 'homepage', 'main', 'index', 'landing'],
            'about': ['about', 'about us', 'about-us', 'company', 'who we are', 'our story'],
            'services': ['services', 'service', 'what we do', 'offerings', 'solutions', 'our services'],
            'portfolio': ['portfolio', 'work', 'projects', 'gallery', 'our work', 'case studies'],
            'contact': ['contact', 'contact us', 'contact-us', 'get in touch', 'reach us', 'location'],
            'blog': ['blog', 'news', 'articles', 'posts'],
            'team': ['team', 'our team', 'members', 'staff', 'our people'],
            'testimonials': ['testimonials', 'reviews', 'what clients say', 'client reviews'],
            'pricing': ['pricing', 'plans', 'packages', 'subscriptions', 'prices'],
            'faq': ['faq', 'questions', 'answers', 'help', 'support', 'frequently asked'],
            'products': ['products', 'shop', 'store', 'merchandise', 'product']
        }
        
        # First, look for exact page names in the query
        # Split query by common separators to find individual page names
        import re
        
        # Common patterns for page lists
        patterns = [
            r'(\w+(?:\s+\w+)*)',  # Match words that could be page names
            r'([^,]+)',  # Match anything between commas
            r'(\w+(?:\s+us)?)',  # Match "contact us" type patterns
        ]
        
        # Extract potential page names from the query
        potential_pages = []
        for pattern in patterns:
            matches = re.findall(pattern, query)
            for match in matches:
                match = match.strip()
                if len(match) > 2:  # Only consider meaningful matches
                    potential_pages.append(match)
        
        # Now match these potential pages against our page mappings
        for potential_page in potential_pages:
            for page_type, variations in page_name_mappings.items():
                if any(variation in potential_page or potential_page in variation for variation in variations):
                    if page_type not in requested_pages:
                        requested_pages.append(page_type)
                        print(f"Found page type '{page_type}' from query: '{potential_page}'")
                    break
        
        # If no pages found with exact matching, try the original keyword approach
        # but be more conservative
        if not requested_pages:
            print("No exact matches found, trying keyword search...")
            for page_type, keywords in page_name_mappings.items():
                for keyword in keywords:
                    if keyword in query:
                        if page_type not in requested_pages:
                            requested_pages.append(page_type)
                            print(f"Found page type '{page_type}' via keyword: '{keyword}'")
                        break
        
        # Check for specific count requests like "I need 5 pages"
        num_pages_match = re.search(r'(\d+)\s+pages?', query)
        if num_pages_match:
            num_pages = int(num_pages_match.group(1))
            print(f"User requested {num_pages} pages, found {len(requested_pages)}")
            
            # Only add more pages if we have fewer than requested AND the user didn't specify exact pages
            if len(requested_pages) < num_pages and len(requested_pages) == 0:
                # User asked for a number but didn't specify which pages
                # Add default pages to meet the count
                available_pages = list(page_name_mappings.keys())
                pages_to_add = min(num_pages, len(available_pages))
                requested_pages = available_pages[:pages_to_add]
                print(f"Added {pages_to_add} default pages to meet count requirement")
            elif len(requested_pages) < num_pages:
                # User specified some pages but we need more to meet the count
                print(f"Warning: User requested {num_pages} pages but only specified {len(requested_pages)}")
                # Don't add extra pages - respect what the user actually asked for
        
        # Only add home page if user explicitly requested it or if no pages were found
        if not requested_pages:
            requested_pages = ['home']
            print("No pages found, defaulting to home page")
        elif 'home' not in requested_pages and len(requested_pages) == 1:
            # If user only specified one page and it's not home, don't add home automatically
            pass
        elif 'home' not in requested_pages:
            # Only add home if user specified multiple pages but didn't include home
            # This is optional - let's not add it automatically
            pass
        
        # Order pages in a logical way, but respect user's order when possible
        ordered_pages = []
        
        # If user specified pages in a certain order, try to maintain that order
        # by checking the original query for the order
        query_lower = query.lower()
        for page_type in requested_pages:
            # Find the position of this page type in the original query
            best_position = -1
            for variation in page_name_mappings.get(page_type, [page_type]):
                pos = query_lower.find(variation)
                if pos != -1 and (best_position == -1 or pos < best_position):
                    best_position = pos
            
            if best_position != -1:
                ordered_pages.append((best_position, page_type))
        
        # Sort by position in query
        ordered_pages.sort(key=lambda x: x[0])
        final_pages = [page_type for _, page_type in ordered_pages]
        
        # If we couldn't determine order from query, use logical order
        if not final_pages:
            # Use the primary pages order for the pages we have
            for page in self.primary_pages:
                if page in requested_pages:
                    final_pages.append(page)
            
            # Add any remaining pages
            for page in requested_pages:
                if page not in final_pages:
                    final_pages.append(page)
        
        print(f"Final ordered pages: {final_pages}")
        return final_pages

    def fetch_pages(self, page_types: List[str]) -> Dict[str, Any]:
        """Fetch pages of the requested types from Supabase - only return exactly what was requested"""
        selected_pages = {}
        missing_pages = []
        
        print(f"Fetching exactly {len(page_types)} pages: {page_types}")
        
        # First attempt - exact category match
        for page_type in page_types:
            print(f"Looking for page type: '{page_type}'")
            
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
                    print(f"✓ Found page for type: '{page_type}' - Title: '{selected_page.get('title', 'No title')}'")
                else:
                    missing_pages.append(page_type)
                    print(f"✗ No pages found for type: '{page_type}' in database")
            except Exception as e:
                missing_pages.append(page_type)
                print(f"✗ Error fetching '{page_type}' pages: {e}")
        
        # Second attempt - for missing pages, try search in content or other fields
        # But be more conservative and only do this if we have very few pages
        if missing_pages and len(selected_pages) < len(page_types) * 0.5:  # Only if we have less than 50% of requested pages
            print(f"⚠️  Searching for alternative pages for: {missing_pages}")
            
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
                            selected_pages[page_type] = fallback_page
                            print(f"✓ Found alternative page for '{page_type}' with content match - Title: '{fallback_page.get('title', 'No title')}'")
                        else:
                            print(f"✗ No alternative found for '{page_type}'")
            except Exception as e:
                print(f"✗ Error finding alternative pages: {e}")
        
        # Final summary
        found_pages = list(selected_pages.keys())
        still_missing = [page for page in page_types if page not in selected_pages]
        
        print(f"\n📊 Page Selection Summary:")
        print(f"   Requested: {page_types}")
        print(f"   Found: {found_pages}")
        if still_missing:
            print(f"   Missing: {still_missing}")
            print(f"   ⚠️  Warning: Some requested pages could not be found")
        
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

    def add_page_to_template(self, channel: ET.Element, page_type: str, page_data: Dict[str, Any], page_id: int, style_description: str = None, palette=None, custom_mapping=None) -> None:
        """Add a page to the XML template"""
        print(f"[DEBUG] add_page_to_template for '{page_type}' with style_description: '{style_description}'")
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
                    modified_data = self._apply_color_palette(parsed_data, style_description, palette, custom_mapping)
                    
                    # Convert back to string with proper formatting
                    elementor_data = json.dumps(modified_data, ensure_ascii=False, separators=(',', ':'))
                    print(f"Applied color palette to page {page_type}")
                except Exception as e:
                    print(f"Error applying color palette to page {page_type}: {e}")
            
            meta_elementor = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
            meta_key = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_key')
            meta_key.text = '_elementor_data'
            meta_value = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_value')
            
            # Fix JSON serialization to prevent double escaping
            # Use plain text instead of CDATA to avoid recursion issues
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

    def _apply_color_palette(self, elementor_data, style_description, palette=None, custom_mapping=None):
        print(f"[DEBUG] _apply_color_palette called with style_description: '{style_description}'")
        # Use provided palette/custom_mapping if available, else fallback to old logic
        if palette is not None:
            print("[DEBUG] Using pre-generated palette for this site")
            used_palette = palette
            used_mapping = custom_mapping
        else:
            # Fallback: generate palette as before (should not happen in multipage flow)
            used_palette, used_mapping = generate_color_palette_with_gpt4o(style_description)
        try:
            # Generate text colors for accessibility
            text_colors = create_accessible_text_colors(used_palette)
            print(f"Generated accessible text colors for the palette")
            # Map the palette to Elementor properties
            elementor_color_map = map_colors_to_elementor(used_palette, text_colors if used_mapping is None else used_mapping)
            print(f"Mapped Elementor properties to colors")
            
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
        print(f"[DEBUG] MultiPageSiteGenerator.create_multi_page_site called with style_description: '{style_description}'")
        print(f"[DEBUG] User query: '{user_query}'")
        
        # Parse the user query to get requested pages
        page_types = self.parse_user_query(user_query)
        print(f"Identified page types: {page_types}")
        
        # Fetch pages from Supabase
        selected_pages = self.fetch_pages(page_types)
        print(f"Selected {len(selected_pages)} pages out of {len(page_types)} requested")
        
        # Check if we have enough pages to proceed
        if len(selected_pages) == 0:
            raise ValueError("No pages could be found for the requested types. Please try different page names or check the database.")
        
        if len(selected_pages) < len(page_types):
            print(f"⚠️  Warning: Only found {len(selected_pages)} out of {len(page_types)} requested pages")
            print(f"   Using: {list(selected_pages.keys())}")
            print(f"   Missing: {[p for p in page_types if p not in selected_pages]}")
        
        # Create a base template
        rss = self.create_base_template()
        channel = rss.find('channel')

        # Generate the color palette and mapping ONCE per site
        palette, custom_mapping = generate_color_palette_with_gpt4o(style_description)
        print(f"[DEBUG] Generated color palette with GPT-4o once for all pages")

        # Ensure palette and mapping are not None
        if palette is None or custom_mapping is None:
            print("ERROR: Palette or mapping is None after GPT-4o call!")
        self.generated_palette = palette
        self.generated_mapping = custom_mapping
        self.generated_style_description = style_description

        # Only add pages that were actually found
        page_id = 1
        actual_pages_used = []
        
        for page_type in page_types:
            if page_type in selected_pages:
                print(f"[DEBUG] Adding page '{page_type}' with style_description: '{style_description}'")
                self.add_page_to_template(channel, page_type, selected_pages[page_type], page_id, style_description, palette, custom_mapping)
                actual_pages_used.append(page_type)
                page_id += 1
            else:
                print(f"[DEBUG] Skipping page '{page_type}' - not found in database")
        
        # Create menu items for navigation - only for pages that were actually used
        menu_id = 100  # Start menu items at ID 100
        for idx, page_type in enumerate(actual_pages_used):
            self.create_menu_item(
                channel,
                selected_pages[page_type].get('title', page_type.capitalize()),
                f'https://example.com/{page_type}/',
                menu_id + idx,
                idx
            )
        
        print(f"✅ Successfully created multi-page site with {len(actual_pages_used)} pages: {actual_pages_used}")
        
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
    
    # Test the exact query the user mentioned
    user_query = "I need home, about, contact us, services"
    output_path = "output/multi_page_site.xml"
    
    print("=== Testing Improved Query Parsing ===")
    print(f"Query: '{user_query}'")
    
    try:
        # Test just the parsing first
        page_types = generator.parse_user_query(user_query)
        print(f"Parsed pages: {page_types}")
        
        # Now test the full generation
        generator.create_multi_page_site(user_query, output_path)
        print(f"Multi-page site generation successful!")
    except Exception as e:
        print(f"Multi-page site generation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
