import os
import json
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Any, Optional, Tuple, Union
from html import unescape
import uuid
from supabase import create_client, Client
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
import traceback
import sys

# Create FastAPI app
app = FastAPI(
    title="Offline WordPress Theme Extractor",
    description="API for extracting and processing WordPress Elementor themes",
    version="1.0.0"
)

# Define request models
class ThemeTransformByIdRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None

class FixedElementorExtractor:
    """Fixed extraction agent with reliable page and section detection"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get Supabase credentials
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.namespaces = {
            'wp': 'http://wordpress.org/export/1.2/',
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
        }
        
        # Section patterns for identification
        self.section_patterns = {
            'hero': ['banner', 'hero', 'main', 'slider', 'home'],
            'about': ['about', 'company', 'who we are', 'story'],
            'services': ['service', 'what we do', 'solutions', 'offerings'],
            'portfolio': ['portfolio', 'work', 'projects', 'gallery'],
            'team': ['team', 'members', 'staff', 'people'],
            'testimonials': ['testimonial', 'review', 'feedback', 'client say'],
            'pricing': ['price', 'package', 'plan', 'subscription'],
            'contact': ['contact', 'reach', 'touch', 'location', 'address'],
            'features': ['feature', 'benefit', 'advantage'],
            'products': ['product', 'shop', 'store'],
            'blog': ['blog', 'news', 'article', 'post'],
            'faq': ['faq', 'question', 'answer'],
            'cta': ['action', 'subscribe', 'register', 'sign up'],
            'clients': ['client', 'partner', 'brand'],
            'skills': ['skill', 'expertise', 'capability']
        }
        
        # Widget type mapping
        self.widget_type_map = {
            'form': 'contact',
            'google_maps': 'map',
            'price-table': 'pricing',
            'testimonial': 'testimonials',
            'portfolio': 'portfolio',
            'team-member': 'team',
            'posts': 'blog'
        }

    def _categorize_page(self, title_text: str) -> str:
        """Categorize a page based on its title"""
        title_lower = title_text.lower()
        
        # Map common page titles to categories
        if any(word in title_lower for word in ['home', 'front', 'main', 'landing']):
            return 'home'
        elif any(word in title_lower for word in ['about', 'company', 'who we are', 'our story']):
            return 'about'
        elif any(word in title_lower for word in ['contact', 'reach', 'get in touch', 'location']):
            return 'contact'
        elif any(word in title_lower for word in ['service', 'what we do', 'offering']):
            return 'services'
        elif any(word in title_lower for word in ['portfolio', 'work', 'project', 'case']):
            return 'portfolio'
        elif any(word in title_lower for word in ['blog', 'news', 'article', 'post']):
            return 'blog'
        elif any(word in title_lower for word in ['shop', 'store', 'product']):
            return 'shop'
        elif any(word in title_lower for word in ['faq', 'help', 'support']):
            return 'faq'
        elif any(word in title_lower for word in ['team', 'staff', 'people']):
            return 'team'
        elif any(word in title_lower for word in ['pricing', 'plan', 'package']):
            return 'pricing'
        elif any(word in title_lower for word in ['testimonial', 'review', 'feedback']):
            return 'testimonials'
        elif any(word in title_lower for word in ['career', 'job', 'position']):
            return 'careers'
        else:
            return 'general'

    def process_theme(self, xml_path_or_id: str) -> Tuple[str, List[Dict], List[Dict]]:
        """Process WordPress theme XML and store in Supabase"""
        theme_id = str(uuid.uuid4())
        
        try:
            # Check if xml_path_or_id is a UUID (theme ID) or a file path
            try:
                uuid.UUID(xml_path_or_id)
                is_theme_id = True
            except ValueError:
                is_theme_id = False
            
            # Handle theme ID or file path appropriately
            if is_theme_id:
                # It's a theme ID, fetch the theme from Supabase
                print(f"Fetching theme {xml_path_or_id} from database...")
                try:
                    result = self.supabase.table('themes').select('*').eq('id', xml_path_or_id).execute()
                    if not result.data:
                        raise ValueError(f"Theme with ID '{xml_path_or_id}' not found in database.")
                    
                    theme_data = result.data[0]
                    theme_id = xml_path_or_id  # Use the existing theme ID
                    
                    # Create a temporary file for the theme XML
                    temp_dir = os.path.join(os.getcwd(), "processing")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_file_path = os.path.join(temp_dir, f"temp_{xml_path_or_id}.xml")
                    
                    # Check for XML content in different possible field names
                    content = None
                    possible_content_fields = ['content', 'xml_content', 'xml_data', 'file_content', 'theme_content', 'data']
                    
                    for field in possible_content_fields:
                        if field in theme_data and theme_data.get(field):
                            content = theme_data.get(field)
                            print(f"Found theme content in field '{field}'")
                            break
                    
                    # If still no content, check if there's a file_path or similar field
                    if not content and ('file_path' in theme_data or 'xml_path' in theme_data):
                        file_path = theme_data.get('file_path') or theme_data.get('xml_path')
                        if file_path and os.path.exists(file_path):
                            print(f"Reading theme content from file: {file_path}")
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                    
                    # If we still don't have content, try to load it from a related table
                    if not content:
                        try:
                            # Check if there's a theme_files or files table with the content
                            related_result = self.supabase.table('theme_files').select('*').eq('theme_id', theme_id).execute()
                            if related_result.data:
                                for file_data in related_result.data:
                                    if 'content' in file_data and file_data.get('content'):
                                        content = file_data.get('content')
                                        print(f"Found theme content in related theme_files table")
                                        break
                        except Exception as e:
                            print(f"Error checking related tables: {e}")
                    
                    # If still no content, raise error
                    if not content:
                        print(f"DEBUG: Theme {xml_path_or_id} has these fields: {list(theme_data.keys())}")
                        print(f"DEBUG: Theme data sample: {str(theme_data)[:500]}...")
                        
                        # Try to check theme_files table 
                        try:
                            print(f"DEBUG: Checking theme_files table for theme content...")
                            files_result = self.supabase.table('theme_files').select('*').eq('theme_id', xml_path_or_id).execute()
                            if files_result.data:
                                print(f"DEBUG: Found {len(files_result.data)} files associated with theme")
                                print(f"DEBUG: File fields: {list(files_result.data[0].keys())}")
                            else:
                                print(f"DEBUG: No files found in theme_files table")
                        except Exception as file_e:
                            print(f"DEBUG: Error checking theme_files: {file_e}")
                            
                        raise ValueError(f"Theme with ID '{xml_path_or_id}' has no content or empty content in database. Available fields: {list(theme_data.keys())}")
                    
                    # Basic validation that content looks like XML
                    if not content.strip().startswith('<?xml') and not content.strip().startswith('<'):
                        raise ValueError(f"Theme content does not appear to be valid XML. Content starts with: {content[:50]}...")
                    
                    # Write the theme data to the temporary file
                    with open(temp_file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    print(f"Wrote theme content to temporary file: {temp_file_path}")
                    
                    # Use the temporary file as the input XML
                    xml_path = temp_file_path
                    
                except Exception as e:
                    raise ValueError(f"Failed to fetch theme from database: {e}")
            else:
                # It's a file path, check if it exists
                xml_path = xml_path_or_id
                if not os.path.exists(xml_path):
                    raise FileNotFoundError(f"XML file '{xml_path}' not found.")
                
                # Read the file content for storage
                with open(xml_path, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
            
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # First store theme metadata
            theme_metadata = self._extract_theme_metadata(root)
            
            # If we're using an existing theme, use its ID
            if is_theme_id:
                theme_metadata['id'] = theme_id
            else:
                theme_metadata['id'] = theme_id
                # Add the XML content to the theme metadata if not already there
                theme_metadata['content'] = xml_content
            
            try:
                # Insert theme first to establish foreign key relationship
                # If using existing theme, this might be an update or insert
                if is_theme_id:
                    # Check if theme exists and update if needed
                    result = self.supabase.table('themes').select('id').eq('id', theme_id).execute()
                    if not result.data:
                        self.supabase.table('themes').insert(theme_metadata).execute()
                    else:
                        # If the theme exists but doesn't have content, update it
                        for field in ['content', 'xml_content']:
                            if field not in theme_data or not theme_data.get(field):
                                try:
                                    # Update content only if it doesn't already exist
                                    self.supabase.table('themes').update({field: xml_content}).eq('id', theme_id).execute()
                                    print(f"Updated theme {theme_id} with XML content in field '{field}'")
                                    break
                                except Exception as update_e:
                                    print(f"Error updating theme with content: {update_e}")
                else:
                    self.supabase.table('themes').insert(theme_metadata).execute()
                    print(f"Stored XML content in database for theme {theme_id}")
            except Exception as e:
                print(f"Failed to store theme metadata: {e}")
                raise
                
            # Initialize extraction data
            extracted_data = {
                'texts': [],
                'colors': [],
                'elementor_data': []
            }

            # Find all Elementor data
            elementor_metas = root.findall(
                ".//wp:postmeta[wp:meta_key='_elementor_data']", 
                namespaces=self.namespaces
            )

            # Process each Elementor meta
            for meta in elementor_metas:
                meta_value = meta.find('wp:meta_value', namespaces=self.namespaces)
                if meta_value is not None and meta_value.text:
                    try:
                        elementor_data = json.loads(meta_value.text)
                        extracted_data['elementor_data'].append(elementor_data)
                        
                        texts = self._extract_texts(elementor_data)
                        extracted_data['texts'].extend(texts)
                        
                        colors = self._extract_colors(elementor_data)
                        extracted_data['colors'].extend(colors)
                        
                    except json.JSONDecodeError:
                        continue

            # Process pages and sections
            pages_data = []
            sections_data = []
            
            for item in root.findall('.//item', namespaces=self.namespaces):
                post_type = item.find('wp:post_type', self.namespaces)
                if post_type is not None and post_type.text == 'page':
                    page_data = self._process_page(item, theme_id)
                    if page_data:
                        pages_data.append(page_data)
                        # Process sections for this page
                        if page_data.get('elementor_data'):
                            try:
                                elementor_data = json.loads(page_data['elementor_data'])
                                is_home_page = page_data.get('category', '').lower() == 'home'
                                sections = self._identify_sections(elementor_data, theme_id, page_data['id'], is_home_page=is_home_page)
                                sections_data.extend(sections)
                            except json.JSONDecodeError:
                                continue

            # Store pages and sections
            if pages_data:
                try:
                    self.supabase.table('pages').insert(pages_data).execute()
                    print(f"Stored {len(pages_data)} pages in database")
                except Exception as e:
                    print(f"Error storing pages: {e}")
                    
            if sections_data:
                try:
                    self.supabase.table('sections').insert(sections_data).execute()
                    print(f"Stored {len(sections_data)} sections in database")
                except Exception as e:
                    print(f"Error storing sections: {e}")

            # Check if transformation data already exists
            transformation_exists = False
            try:
                existing_result = self.supabase.table('transformation_data').select('id').eq('theme_id', theme_id).execute()
                if existing_result.data and len(existing_result.data) > 0:
                    transformation_exists = True
                    print(f"Transformation data already exists for theme {theme_id}")
            except Exception as e:
                print(f"Error checking existing transformation data: {e}")

            # Store transformation data if it doesn't exist
            if not transformation_exists:
                try:
                    # Create transformation record
                    # Store texts directly without wrapper structure
                    text_transformations = []
                    
                    # Store all texts directly (including duplicates)
                    for text in extracted_data['texts']:
                        if len(text.strip()) > 0:  # Skip empty texts
                            text_transformations.append(text)  # Store the text directly
                    
                    # Store colors directly without from/to structure
                    color_mappings = []
                    
                    # Store all colors directly (including duplicates)
                    for color in extracted_data['colors']:
                        if color:  # Skip empty colors
                            color_mappings.append(color)  # Store the color directly
                    
                    # Final transformation structure
                    transformation_record = {
                        'id': str(uuid.uuid4()),
                        'theme_id': theme_id,
                        'texts': text_transformations,  # Store all texts directly
                        'colors': color_mappings,  # Store all colors directly
                        'elementor_data': {
                            'sections': extracted_data['elementor_data']
                        },
                        'created_at': datetime.utcnow().isoformat()
                    }
                    
                    # Insert into transformation_data table
                    self.supabase.table('transformation_data').insert(transformation_record).execute()
                    print(f"Stored transformation data with {len(text_transformations)} texts and {len(color_mappings)} colors (including duplicates)")
                
                except Exception as e:
                    print(f"Failed to store transformation data: {e}")
                    traceback.print_exc()

            # Clean up temporary file if we created one
            if is_theme_id and os.path.exists(xml_path):
                try:
                    os.remove(xml_path)
                except Exception as e:
                    print(f"Failed to remove temporary file: {e}")
            
            return theme_id, pages_data, sections_data
            
        except Exception as e:
            print(f"Error processing theme: {e}")
            traceback.print_exc()
            raise

    def extract_content_only(self, xml_file: str) -> Tuple[List[Dict], List[Dict]]:
        """Extract content from XML without creating a new theme record"""
        print(f"Extracting content from {xml_file}...")
        
        try:
            # Parse XML
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Initialize data structures
            pages_data = []
            sections_data = []
            
            # Process all items (pages)
            items = root.findall(".//item")
            
            # Initialize section counter
            section_id_counter = 1
            
            for item in items:
                # Extract page information
                title = item.find("title")
                post_id = item.find(".//wp:post_id", self.namespaces)
                post_type = item.find(".//wp:post_type", self.namespaces)
                
                if title is None or post_id is None:
                    continue
                    
                title_text = title.text or "Untitled"
                post_id_text = post_id.text
                post_type_text = post_type.text if post_type is not None else "page"
                
                # Skip if not a page
                if post_type_text != "page":
                    continue
                    
                # Get page content
                content = item.find(".//content:encoded", self.namespaces)
                if content is None or not content.text:
                    continue
                    
                # Extract page category from title
                page_category = self._categorize_page(title_text)
                
                # Store page data
                page_data = {
                    "id": post_id_text,
                    "title": title_text,
                    "category": page_category,
                    "content": content.text
                }
                
                pages_data.append(page_data)
                
                # Extract Elementor sections
                elementor_data = None
                for meta in item.findall('wp:postmeta', self.namespaces):
                    meta_key = meta.find('wp:meta_key', self.namespaces)
                    meta_value = meta.find('wp:meta_value', self.namespaces)
                    
                    if meta_key is not None and meta_value is not None:
                        if meta_key.text == '_elementor_data' and meta_value.text:
                            try:
                                elementor_data = json.loads(meta_value.text)
                                is_home_page = page_category.lower() == 'home'
                                sections = self._identify_sections(elementor_data, "", page_data["id"], is_home_page=is_home_page)
                                sections_data.extend(sections)
                            except json.JSONDecodeError:
                                continue
            
            print(f"Extracted {len(pages_data)} pages and {len(sections_data)} sections")
            return pages_data, sections_data
            
        except ET.ParseError as e:
            print(f"XML parsing error: {e}")
            raise
        except Exception as e:
            print(f"Error extracting content: {e}")
            raise

    def _process_page(self, page_item: ET.Element, theme_id: str) -> Optional[Dict]:
        """Process individual page data"""
        title = page_item.find('title')
        if title is None:
            return None
            
        content = page_item.find('content:encoded', self.namespaces)
        post_name = page_item.find('wp:post_name', self.namespaces)
        post_id = page_item.find('wp:post_id', self.namespaces)
        
        # Extract Elementor data
        elementor_data = None
        page_template = None
        
        for meta in page_item.findall('wp:postmeta', self.namespaces):
            meta_key = meta.find('wp:meta_key', self.namespaces)
            meta_value = meta.find('wp:meta_value', self.namespaces)
            
            if meta_key is not None and meta_value is not None:
                if meta_key.text == '_elementor_data':
                    elementor_data = meta_value.text
                elif meta_key.text == '_wp_page_template':
                    page_template = meta_value.text
        
        # Determine page category based on title or template
        page_category = 'general'  # Default category
        title_text = title.text.lower()
        
        # Map common page titles to categories
        if any(word in title_text for word in ['home', 'front', 'main']):
            page_category = 'home'
        elif any(word in title_text for word in ['about', 'company']):
            page_category = 'about'
        elif any(word in title_text for word in ['contact', 'reach']):
            page_category = 'contact'
        elif any(word in title_text for word in ['service', 'product']):
            page_category = 'service'
        elif any(word in title_text for word in ['blog', 'news']):
            page_category = 'blog'
        
        return {
            'id': str(uuid.uuid4()),
            'theme_id': theme_id,
            'title': title.text,
            'category': page_category,  # Added category field
            'elementor_data': elementor_data,
            'content': content.text if content is not None else '',
            'created_at': datetime.utcnow().isoformat()
        }

    def _identify_sections(self, elementor_data: Any, theme_id: str, page_id: str, is_home_page: bool = False) -> List[Dict]:
        """Identify only top-level sections/containers from Elementor data. If is_home_page, first section/container is 'main'."""
        sections = []
        first_section = True

        def process_layout_element(element, parent_is_layout=False):
            nonlocal first_section
            if not isinstance(element, dict):
                return

            el_type = element.get('elType')
            is_layout = el_type in ('section', 'container')

            # Only treat as section if not nested inside another layout
            if is_layout and not parent_is_layout:
                section_id = element.get('id')
                section_type = None
                section_content = []

                # Recursively process child elements for categorization
                for child in element.get('elements', []):
                    if isinstance(child, dict):
                        if child.get('elType') == 'widget':
                            section_type_candidate = self._analyze_widget_content(child)
                            if section_type_candidate and not section_type:
                                section_type = section_type_candidate
                            section_content.append(child)
                        # Do NOT treat nested containers/sections as sections
                        # But still process their widgets for categorization
                        elif child.get('elType') in ('section', 'container', 'column'):
                            for widget in child.get('elements', []):
                                if widget.get('elType') == 'widget':
                                    section_type_candidate = self._analyze_widget_content(widget)
                                    if section_type_candidate and not section_type:
                                        section_type = section_type_candidate
                                    section_content.append(widget)

                # Special handling for first section/container of home page
                if first_section:
                    first_section = False
                    if is_home_page:
                        section_type = section_type or 'main'
                section_type = section_type or 'general'

                sections.append({
                    'id': str(uuid.uuid4()),
                    'theme_id': theme_id,
                    'page_id': page_id,
                    'category': section_type,
                    'content': json.dumps(element),
                    'created_at': datetime.utcnow().isoformat()
                })

            # Always process children, but set parent_is_layout=True if this is a layout
            for child in element.get('elements', []):
                if isinstance(child, dict):
                    process_layout_element(child, parent_is_layout=is_layout)

        if isinstance(elementor_data, list):
            for item in elementor_data:
                process_layout_element(item)
        else:
            process_layout_element(elementor_data)

        return sections

    def _analyze_widget_content(self, widget: Dict) -> Optional[str]:
        """Analyze widget content to determine section type"""
        if not isinstance(widget, dict):
            return None
            
        widget_type = widget.get('widgetType', '')
        settings = widget.get('settings', {})
        
        if not isinstance(settings, dict):
            return None
            
        # Get text content from settings
        content_fields = ['title', 'heading', 'text', 'subtitle', 'description',
                         'content', 'button_text', 'tab_title']
        
        content = ' '.join([
            str(settings.get(field, '')).lower() 
            for field in content_fields 
            if settings.get(field)
        ])
        
        # Check widget type first
        if widget_type in self.widget_type_map:
            return self.widget_type_map[widget_type]
        
        # Check content patterns
        for section_type, patterns in self.section_patterns.items():
            if any(pattern in content for pattern in patterns):
                return section_type
                
        return None

    def _extract_theme_metadata(self, root: ET.Element) -> Dict:
        """Extract theme metadata"""
        title = root.find('.//channel/title')
        description = root.find('.//channel/description')
        
        return {
            'title': title.text if title is not None else 'Untitled Theme',
            'description': description.text if description is not None else '',
            'status': 'active'
        }

    def _extract_texts(self, data: Any) -> List[str]:
        """Extract text content from Elementor data, preserving duplicates, supporting containers and lists in settings."""
        texts = []
        def extract_recursive(item):
            if isinstance(item, dict):
                # Extract text fields from widget settings
                if item.get('elType') == 'widget':
                    settings = item.get('settings', {})
                    if isinstance(settings, dict):
                        for field in ['title', 'heading', 'text', 'subtitle', 'description', 'content', 'button_text', 'tab_title', 'editor', 'address']:
                            value = settings.get(field)
                            if value and isinstance(value, str):
                                texts.append(value)
                            elif isinstance(value, (dict, list)):
                                extract_recursive(value)
                    elif isinstance(settings, list):
                        for sub in settings:
                            extract_recursive(sub)
                # Recurse into elements (for containers, sections, columns, etc.)
                for child in item.get('elements', []):
                    extract_recursive(child)
            elif isinstance(item, list):
                for sub in item:
                    extract_recursive(sub)
        extract_recursive(data)
        return texts

    def _extract_colors(self, data: Any) -> List[str]:
        """Extract color values from Elementor data, supporting containers and lists in settings."""
        colors = []
        def extract_recursive(item):
            if isinstance(item, dict):
                settings = item.get('settings', {})
                if isinstance(settings, dict):
                    for key, value in settings.items():
                        if isinstance(value, str) and (key.endswith('color') or 'color' in key):
                            if re.match(r'^#([A-Fa-f0-9]{3,8})$', value) or value.startswith('rgba'):
                                colors.append(value)
                        elif isinstance(value, (dict, list)):
                            extract_recursive(value)
                elif isinstance(settings, list):
                    for sub in settings:
                        extract_recursive(sub)
                # Recurse into elements
                for child in item.get('elements', []):
                    extract_recursive(child)
            elif isinstance(item, list):
                for sub in item:
                    extract_recursive(sub)
        extract_recursive(data)
        return colors

    def _extract_transformation_data(self, elementor_data: Any) -> Dict:
        """Extract transformation data like texts and colors, preserving duplicates"""
        extracted_data = {
            'texts': self._extract_texts(elementor_data),  # Keep all texts
            'colors': self._extract_colors(elementor_data),  # Keep all colors
            'elementor_data': [elementor_data]
        }
        return extracted_data

    def _clean_html_content(self, html_content: str) -> str:
        """Clean HTML content by removing tags and normalizing whitespace"""
        if not html_content:
            return ""
        # Remove <p> and </p> tags
        text = re.sub(r'</?p>', '', str(html_content))
        # Remove any other HTML tags while preserving content
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove HTML entities
        text = unescape(text)
        # Normalize whitespace and clean up
        text = re.sub(r'\s+', ' ', text).strip()
        return text

if __name__ == "__main__":
    try:
        extractor = FixedElementorExtractor()
        theme_id, pages, sections = extractor.process_theme("input/gbptheme.WordPress.2024-11-13.xml")
        print(f"Successfully processed theme: {theme_id}")
        print(f"Extracted {len(pages)} pages and {len(sections)} sections")
    except ValueError as e:
        print(f"Configuration error: {e}")
    except Exception as e:
        print(f"Processing error: {e}")

@app.post("/upload-theme-xml/{theme_id}")
async def upload_theme_xml(theme_id: str, file: UploadFile = File(...)):
    """Upload XML file and associate it with a theme ID in the database"""
    try:
        # Validate theme ID format
        try:
            uuid.UUID(theme_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid theme ID format. Expected UUID.")
            
        # Validate file extension
        if not file.filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="Only XML files are supported")
            
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Basic validation that content looks like XML
        if not content_str.strip().startswith('<?xml') and not content_str.strip().startswith('<'):
            raise HTTPException(status_code=400, detail=f"File does not appear to be valid XML. Content starts with: {content_str[:50]}...")
            
        # Get Supabase credentials
        load_dotenv()
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise HTTPException(status_code=500, detail="SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        supabase = create_client(supabase_url, supabase_key)
        
        # Check if theme exists
        result = supabase.table('themes').select('id').eq('id', theme_id).execute()
        
        if not result.data:
            # Create new theme record if it doesn't exist
            theme_metadata = {
                'id': theme_id,
                'title': file.filename.replace('.xml', ''),
                'description': f"Theme uploaded on {datetime.utcnow().isoformat()}",
                'status': 'active',
                'content': content_str,
                'created_at': datetime.utcnow().isoformat()
            }
            supabase.table('themes').insert(theme_metadata).execute()
            return {"message": f"Created new theme with ID {theme_id} and stored XML content", "theme_id": theme_id}
        else:
            # Update existing theme with XML content
            supabase.table('themes').update({
                'content': content_str,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', theme_id).execute()
            return {"message": f"Updated theme {theme_id} with XML content", "theme_id": theme_id}
            
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error uploading theme XML: {str(e)}")

#usage
