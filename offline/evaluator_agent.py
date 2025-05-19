import os
import json
import uuid
from typing import Dict, List, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import openai

class SectionEvaluator:
    """Agent that evaluates and categorizes Elementor sections using GPT-4o"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get Supabase credentials
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        # Get OpenAI API key
        openai_api_key = os.getenv('OPENAI_API_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in .env file")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        openai.api_key = openai_api_key
        
        # Define section categories
        self.section_categories = [
            'hero', 'about', 'services', 'features', 'portfolio', 'team',
            'testimonials', 'pricing', 'contact', 'faq', 'cta', 'clients',
            'footer', 'blog', 'products', 'gallery', 'skills', 'map'
        ]
    
    def evaluate_theme_sections(self, theme_id: str) -> Dict[str, Any]:
        """Evaluate all sections in a theme and update their categories, except 'main' sections (case-insensitive, trimmed)."""
        try:
            result = self.supabase.table('sections').select('*').eq('theme_id', theme_id).execute()
            if not result.data:
                raise ValueError(f"No sections found for theme ID: {theme_id}")
            sections = result.data
            print(f"Found {len(sections)} sections to evaluate for theme ID: {theme_id}")
            print("Using enhanced section analysis with complete Elementor data")
            evaluation_results = []
            for section in sections:
                try:
                    section_id = section.get('id')
                    current_category = section.get('category')
                    content = section.get('content')
                    # Skip if no content or if section is 'main' (case-insensitive, trimmed)
                    if not content:
                        print(f"Skipping section {section_id} - no content")
                        continue
                    if current_category and str(current_category).strip().lower() == 'main':
                        print(f"Skipping section {section_id} - category is 'main' (no evaluation, no update)")
                        evaluation_results.append({
                            'section_id': section_id,
                            'old_category': current_category,
                            'new_category': current_category,
                            'updated': False,
                            'skipped_main': True
                        })
                        continue
                    print(f"\nAnalyzing section {section_id}:")
                    print(f"Current category: {current_category}")
                    print(f"Using complete Elementor data for analysis")
                    # Evaluate the section with complete Elementor data
                    new_category = self._evaluate_section_content(content, current_category)
                    if new_category != current_category:
                        self._update_section_category(section_id, new_category)
                        print(f"✓ Updated section {section_id} category from '{current_category}' to '{new_category}'")
                    else:
                        print(f"✓ Section {section_id} category remains '{current_category}'")
                    evaluation_results.append({
                        'section_id': section_id,
                        'old_category': current_category,
                        'new_category': new_category,
                        'updated': new_category != current_category
                    })
                except Exception as e:
                    print(f"Error processing section {section.get('id')}: {e}")
                    evaluation_results.append({
                        'section_id': section.get('id'),
                        'error': str(e)
                    })
            return {
                'theme_id': theme_id,
                'total_sections': len(sections),
                'sections_evaluated': len(evaluation_results),
                'sections_updated': sum(1 for r in evaluation_results if r.get('updated', False)),
                'evaluation_results': evaluation_results
            }
        except Exception as e:
            print(f"Error evaluating theme sections: {e}")
            return {
                'theme_id': theme_id,
                'error': str(e)
            }

    def _evaluate_section_content(self, content_json: str, current_category: str) -> str:
        """Evaluate section content using GPT-4o to determine its category, with special prompt for non-hero."""
        try:
            prompt = f"""
            You are an expert at analyzing WordPress Elementor sections.\n\nI'll provide you with the complete Elementor data for a section, and you need to categorize it.\n\nThe possible categories are: {', '.join(self.section_categories)}\n\nCurrent category: {current_category}\n\nIMPORTANT: All sections you are given are NOT hero sections. Even if the layout looks like a hero/banner, you must use the content to determine the true category (for example, contact us, about, etc).\n\nComplete Elementor data for the section:\n{content_json}\n\nBased on this complete Elementor data, what category best describes this section?\nAnalyze the structure, widgets, content, and purpose of this section.\nRespond with ONLY the category name, nothing else.\n"""
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You analyze WordPress Elementor sections and categorize them accurately based on their complete data. Respond with only the category name."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=50
            )
            category = response.choices[0].message.content
            if category in self.section_categories:
                return category
            else:
                for valid_category in self.section_categories:
                    if valid_category in category:
                        return valid_category
                print(f"Invalid category detected: '{category}', keeping current: '{current_category}'")
                return current_category
        except Exception as e:
            print(f"Error evaluating section content: {e}")
            return current_category
    
    def _update_section_category(self, section_id: str, new_category: str) -> None:
        """Update the category of a section in the database"""
        try:
            self.supabase.table('sections').update({'category': new_category}).eq('id', section_id).execute()
        except Exception as e:
            print(f"Error updating section category: {e}")
            raise
    
    def _extract_text_from_section(self, data: Any) -> List[Dict[str, str]]:
        """Recursively extract text from Elementor section data"""
        texts_list = []
        
        def extract_recursive(data):
            if isinstance(data, dict):
                # Check for text content in this item
                for key in ['text', 'title', 'heading', 'label', 'button_text']:
                    if key in data and isinstance(data[key], str) and len(data[key].strip()) > 0:
                        texts_list.append({
                            'text': data[key].strip(),
                            'type': key
                        })
                        break
                
                # Check for widget type
                if 'widgetType' in data:
                    texts_list.append({
                        'text': f"Widget type: {data['widgetType']}",
                        'type': 'widget_type'
                    })
                
                # Recursively check all values
                for value in data.values():
                    extract_recursive(value)
            elif isinstance(data, list):
                # Check all items in the list
                for item in data:
                    extract_recursive(item)
        
        # Start recursive extraction
        if 'section_data' in data:
            extract_recursive(data['section_data'])
        elif 'widgets' in data:
            extract_recursive(data['widgets'])
        else:
            extract_recursive(data)
        
        return texts_list
        
    def _extract_structure_from_section(self, data: Any) -> Dict[str, Any]:
        """Extract structural information from Elementor section data"""
        structure_info = {
            'widget_types': [],
            'layout_structure': {},
            'element_count': 0,
            'has_form': False,
            'has_images': False,
            'has_buttons': False,
            'has_icons': False,
            'has_maps': False,
            'has_pricing_tables': False,
            'has_testimonials': False,
            'has_team_members': False,
            'has_portfolio': False,
            'has_gallery': False,
            'has_products': False,
            'has_posts': False,
            'has_video': False,
            'section_attributes': {}
        }
        
        def extract_structure_recursive(data, path='root'):
            if isinstance(data, dict):
                # Track element count
                structure_info['element_count'] += 1
                
                # Extract widget type
                if 'widgetType' in data:
                    widget_type = data['widgetType']
                    structure_info['widget_types'].append(widget_type)
                    
                    # Check for specific widget types
                    if 'form' in widget_type.lower():
                        structure_info['has_form'] = True
                    elif any(img_term in widget_type.lower() for img_term in ['image', 'photo', 'gallery', 'carousel']):
                        structure_info['has_images'] = True
                    elif 'button' in widget_type.lower():
                        structure_info['has_buttons'] = True
                    elif 'icon' in widget_type.lower():
                        structure_info['has_icons'] = True
                    elif any(map_term in widget_type.lower() for map_term in ['map', 'location', 'google-map']):
                        structure_info['has_maps'] = True
                    elif any(price_term in widget_type.lower() for price_term in ['price', 'pricing', 'plan']):
                        structure_info['has_pricing_tables'] = True
                    elif any(test_term in widget_type.lower() for test_term in ['testimonial', 'review']):
                        structure_info['has_testimonials'] = True
                    elif any(team_term in widget_type.lower() for team_term in ['team', 'member', 'person', 'staff']):
                        structure_info['has_team_members'] = True
                    elif 'portfolio' in widget_type.lower():
                        structure_info['has_portfolio'] = True
                    elif 'gallery' in widget_type.lower():
                        structure_info['has_gallery'] = True
                    elif any(product_term in widget_type.lower() for product_term in ['product', 'woocommerce']):
                        structure_info['has_products'] = True
                    elif any(post_term in widget_type.lower() for post_term in ['post', 'blog', 'article']):
                        structure_info['has_posts'] = True
                    elif any(video_term in widget_type.lower() for video_term in ['video', 'youtube', 'vimeo']):
                        structure_info['has_video'] = True
                
                # Extract section attributes
                if 'settings' in data and isinstance(data['settings'], dict):
                    # Look for section-specific attributes
                    if 'background_background' in data['settings']:
                        structure_info['section_attributes']['background_type'] = data['settings']['background_background']
                    
                    # Check for section height
                    if 'height' in data['settings']:
                        structure_info['section_attributes']['height'] = data['settings']['height']
                    
                    # Check for section layout
                    if 'layout' in data['settings']:
                        structure_info['section_attributes']['layout'] = data['settings']['layout']
                    
                    # Check for content width
                    if 'content_width' in data['settings']:
                        structure_info['section_attributes']['content_width'] = data['settings']['content_width']
                    
                    # Check for section style
                    if 'style' in data['settings']:
                        structure_info['section_attributes']['style'] = data['settings']['style']
                
                # Track layout structure
                if 'elements' in data and isinstance(data['elements'], list):
                    structure_info['layout_structure'][path] = len(data['elements'])
                
                # Recursively process all values
                for key, value in data.items():
                    if key == 'elements' and isinstance(value, list):
                        for i, element in enumerate(value):
                            extract_structure_recursive(element, f"{path}.{key}[{i}]")
                    else:
                        extract_structure_recursive(value, f"{path}.{key}")
            
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    extract_structure_recursive(item, f"{path}[{i}]")
        
        # Start recursive extraction
        if 'section_data' in data:
            extract_structure_recursive(data['section_data'])
        elif 'widgets' in data:
            extract_structure_recursive(data['widgets'])
        else:
            extract_structure_recursive(data)
        
        return structure_info
