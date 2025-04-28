import datetime
import json
from openai import OpenAI
import re
from typing import Dict, List, Any
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import random
import uuid
import traceback
import html

class ContentTransformationAgent:
    """Agent responsible for transforming extracted content using GPT-4"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get OpenAI and Supabase credentials
        openai_api_key = os.getenv('OPENAI_API_KEY')
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not all([openai_api_key, supabase_url, supabase_key]):
            raise ValueError("Missing required environment variables")
            
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.client = OpenAI(api_key=openai_api_key)
        self.batch_size = 5

    def transform_theme_content(self, theme_id: str, style_description: str, filtered_pages: List[Dict] = None, filtered_sections: List[Dict] = None) -> Dict:
        """Transform theme content based on style description"""
        try:
            # Fetch transformation data for the theme if not using filtered content
            if not filtered_pages and not filtered_sections:
                result = self.supabase.table('transformation_data')\
                    .select('*')\
                    .eq('theme_id', theme_id)\
                    .execute()
                    
                # If no transformation data exists, generate new data
                if not result.data:
                    transformation_data = self._generate_new_transformation_data(theme_id, style_description)
                else:
                    transformation_data = result.data[0]
                
                texts_to_transform = transformation_data.get('texts', [])
                colors_to_transform = transformation_data.get('colors', [])
            else:
                # Use filtered content
                texts_to_transform = []
                colors_to_transform = []
                
                # Extract texts and colors from filtered pages and sections
                for page in filtered_pages:
                    if 'content' in page:
                        texts_to_transform.extend(self._extract_texts_from_content(page['content']))
                        colors_to_transform.extend(self._extract_colors_from_content(page['content']))
                
                for section in filtered_sections:
                    if 'content' in section:
                        try:
                            section_data = json.loads(section['content'])
                            texts_from_section = []
                            self.extract_text_from_section(section_data, texts_from_section)
                            texts_to_transform.extend([t['text'] for t in texts_from_section])
                        except:
                            # If we can't parse JSON, try direct text extraction
                            texts_to_transform.extend(self._extract_texts_from_content(section['content']))
                        colors_to_transform.extend(self._extract_colors_from_content(section['content']))
                
                # Remove duplicates while preserving order
                texts_to_transform = list(dict.fromkeys(texts_to_transform))
                colors_to_transform = list(dict.fromkeys(colors_to_transform))
            
            print(f"Loaded {len(texts_to_transform)} texts and {len(colors_to_transform)} colors")
            
            # Transform content using the generate_transformed_content method directly
            transformed_content = self._generate_transformed_content(texts_to_transform, colors_to_transform, style_description)
            
            # Transform colors
            transformed_colors = self._transform_colors(colors_to_transform, style_description)
            
            return {
                'text_transformations': transformed_content.get('text_transformations', []),
                'color_palette': transformed_colors
            }
            
        except Exception as e:
            print(f"Error transforming content: {e}")
            traceback.print_exc()
            raise

    def _extract_texts_from_content(self, content: str) -> List[str]:
        """Extract text content from HTML/XML content"""
        if not content:
            return []
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', content)
        # Unescape HTML entities
        text = html.unescape(text)
        # Split into sentences or meaningful chunks
        chunks = re.split(r'[.!?]+', text)
        # Clean and filter chunks
        return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 3]

    def _extract_colors_from_content(self, content: str) -> List[str]:
        """Extract color codes from content"""
        if not content:
            return []
        
        # Find hex color codes
        hex_colors = re.findall(r'#(?:[0-9a-fA-F]{3}){1,2}\b', content)
        # Find rgb/rgba color codes
        rgb_colors = re.findall(r'rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)', content)
        rgba_colors = re.findall(r'rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[\d.]+\s*\)', content)
        
        return hex_colors + rgb_colors + rgba_colors

    def _generate_new_transformation_data(self, theme_id: str, style_description: str) -> Dict:
        """Generate new transformation data by extracting text and colors from database"""
        texts = []
        colors = []
        
        # Extract texts from sections
        try:
            # Fetch sections
            sections_result = self.supabase.table('sections') \
                .select('*') \
                .limit(100) \
                .execute()
                
            if sections_result.data:
                for section in sections_result.data:
                    # Extract texts from the section
                    section_content = section.get('content')
                    if section_content:
                        try:
                            section_data = json.loads(section_content)
                            texts_from_section = []
                            self.extract_text_from_section(section_data, texts_from_section)
                            texts.extend([t['text'] for t in texts_from_section])
                        except Exception as e:
                            print(f"Error parsing section content: {e}")
        except Exception as e:
            print(f"Error fetching sections: {e}")
            
        # Get unique texts with minimum length
        unique_texts = list(set([text for text in texts if len(text.split()) >= 3]))
        print(f"Found {len(unique_texts)} unique texts from sections")
        
        # Limit sample size if there are too many texts
        if len(unique_texts) > 30:
            unique_texts = random.sample(unique_texts, 30)
        
        # Default colors if none found
        default_colors = ['#2989CE', '#16202F', '#E22E40', '#FFFFFF', '#757A81']
        colors = colors or default_colors
        
        return {
            'theme_id': theme_id,
            'texts': unique_texts,
            'colors': colors
        }

    def _generate_transformed_content(self, texts: List[str], colors: List[str], style_description: str) -> Dict:
        """Generate transformed content for texts and colors"""
        try:
            # Filter out empty or very short texts
            valid_texts = [text for text in texts if text and len(text.strip()) > 3]
            
            # Process texts in smaller batches to avoid token limits
            batch_size = 10
            transformed_pairs = []
            
            for i in range(0, len(valid_texts), batch_size):
                batch = valid_texts[i:i + batch_size]
                
                messages = [
                    {
                        "role": "system",
                        "content": """You are a professional content transformer for a WordPress theme. Transform each text to match the requested style while:
                        1. Always generating a new transformed version, never returning text unchanged
                        2. Preserving the core meaning and key information
                        3. Maintaining similar length and structure
                        4. Making content relevant to the requested style/business type
                        5. Keeping function words (buttons, labels, etc.) concise and action-oriented
                        Format: For each text return exactly:
                        ORIGINAL: [original text]
                        NEW: [transformed text]"""
                    },
                    {
                        "role": "user",
                        "content": f"""Transform these texts for: {style_description}

                        Original texts:
                        {json.dumps(batch, indent=2)}

                        Return each transformation in the format:
                        ORIGINAL: [text]
                        NEW: [transformed text]"""
                    }
                ]
                
                try:
                    response = self.client.chat.completions.create(
                        model="gpt-3.5-turbo-0125",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=2048
                    )
                    
                    # Parse response
                    response_text = response.choices[0].message.content
                    pairs = re.split(r'ORIGINAL:', response_text)[1:]  # Skip empty first split
                    
                    for pair in pairs:
                        try:
                            parts = pair.split('NEW:', 1)
                            if len(parts) == 2:
                                original = parts[0].strip()
                                transformed = parts[1].strip()
                                transformed = re.sub(r'ORIGINAL:.*', '', transformed).strip()
                                transformed = re.sub(r'===.*===', '', transformed).strip()
                                
                                transformed_pairs.append({
                                    "original": original,
                                    "transformed": transformed
                                })
                        except Exception as e:
                            print(f"Error parsing transformation pair: {e}")
                            continue
                            
                except Exception as e:
                    print(f"Error in batch transformation: {e}")
                    # For failed batches, keep original texts
                    for text in batch:
                        transformed_pairs.append({
                            "original": text,
                            "transformed": text
                        })
            
            # Transform colors
            transformed_colors = self._transform_colors(colors, style_description)
            
            return {
                "text_transformations": transformed_pairs,
                "color_palette": transformed_colors.get('color_palette', {})
            }
            
        except Exception as e:
            print(f"Error generating transformed content: {e}")
            return {
                "text_transformations": [{"original": t, "transformed": t} for t in texts],
                "color_palette": {"original_colors": colors, "new_colors": colors}
            }

    def _transform_colors(self, colors: List[str], style_description: str) -> Dict:
        """Transform colors according to style description"""
        try:
            # Remove duplicates while preserving order
            unique_colors = []
            [unique_colors.append(c) for c in colors if c not in unique_colors]
            
            messages = [
                {
                    "role": "system",
                    "content": """You are a color palette generator for WordPress themes.
                    Generate a new professional color scheme based on the style description.
                    Return exactly 5-7 hex colors that work well together.
                    Format the response exactly as:
                    NEW COLORS: [list of hex codes]
                    NOTES: [brief explanation of color choices]"""
                },
                {
                    "role": "user",
                    "content": f"""Create a new color palette for: {style_description}

                    Current colors: {json.dumps(unique_colors)}
                    
                    Return new hex colors that match the style.
                    Must include primary, secondary, accent, text, and background colors."""
                }
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
            
            response_text = response.choices[0].message.content
            
            # Extract new colors
            new_colors = re.findall(r'#[0-9a-fA-F]{6}\b', response_text)
            
            # Extract notes
            notes = ""
            notes_match = re.search(r'NOTES:\s*(.*?)(?=$|\n\n)', response_text, re.DOTALL)
            if notes_match:
                notes = notes_match.group(1).strip()
            
            # Ensure we have enough colors
            while len(new_colors) < len(unique_colors):
                new_colors.append(new_colors[len(new_colors) % len(new_colors)] if new_colors else "#000000")
            
            return {
                "color_palette": {
                    "original_colors": unique_colors,
                    "new_colors": new_colors[:len(unique_colors)]  # Match original length
                },
                "transformation_notes": notes
            }
            
        except Exception as e:
            print(f"Error transforming colors: {e}")
            return {
                "color_palette": {
                    "original_colors": colors,
                    "new_colors": colors
                },
                "transformation_notes": f"Error: {str(e)}"
            }

    def extract_colors_from_description(self, description: str) -> List[Dict[str, str]]:
        """Extract color information from the style description"""
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
            'fuchsia': '#FF00FF'
        }
        
        # Color patterns for modern design
        modern_color_palettes = [
            # Modern minimal
            ['#FFFFFF', '#F8F9FA', '#E9ECEF', '#DEE2E6', '#212529'],
            # Material-inspired
            ['#3F51B5', '#2196F3', '#4CAF50', '#FFC107', '#FF5722'],
            # Soft pastels
            ['#F8BBD0', '#B2EBF2', '#C8E6C9', '#FFECB3', '#D1C4E9'],
            # Corporate blues
            ['#1565C0', '#1976D2', '#1E88E5', '#2196F3', '#BBDEFB'],
            # Dark mode
            ['#121212', '#1E1E1E', '#262626', '#404040', '#FFFFFF'],
            # Neon/vibrant
            ['#FF1744', '#00E676', '#00B0FF', '#FFEA00', '#D500F9'],
            # Bold contrasts
            ['#FFFFFF', '#212121', '#FFC107', '#1976D2', '#D32F2F']
        ]
        
        # Extract color names from the description
        description = description.lower()
        colors_mentioned = []
        
        for color_name in color_map:
            if color_name in description:
                colors_mentioned.append({
                    'name': color_name,
                    'hex': color_map[color_name]
                })
                
        # Generate a color palette based on description
        selected_palette = []
        
        # If specific colors are mentioned, use them as primary colors
        if colors_mentioned:
            for color in colors_mentioned[:5]:  # Limit to 5 colors
                selected_palette.append(color['hex'])
                
            # Fill in with a complementary palette if needed
            if len(selected_palette) < 5:
                # Find suitable palette based on the mentioned colors
                best_match_palette = random.choice(modern_color_palettes)
                
                # Add colors from selected palette until we have 5 colors
                for color in best_match_palette:
                    if color not in selected_palette and len(selected_palette) < 5:
                        selected_palette.append(color)
        else:
            # No colors mentioned, select based on style keywords
            modern_keywords = ['modern', 'clean', 'minimal', 'simple']
            corporate_keywords = ['corporate', 'professional', 'business', 'formal']
            vibrant_keywords = ['vibrant', 'colorful', 'bright', 'bold', 'neon']
            dark_keywords = ['dark', 'black', 'night', 'contrast']
            soft_keywords = ['soft', 'pastel', 'gentle', 'light']
            
            if any(keyword in description for keyword in modern_keywords):
                selected_palette = modern_color_palettes[0]
            elif any(keyword in description for keyword in corporate_keywords):
                selected_palette = modern_color_palettes[2]
            elif any(keyword in description for keyword in vibrant_keywords):
                selected_palette = modern_color_palettes[5]
            elif any(keyword in description for keyword in dark_keywords):
                selected_palette = modern_color_palettes[4]
            elif any(keyword in description for keyword in soft_keywords):
                selected_palette = modern_color_palettes[2]
            else:
                # Default to a random modern palette
                selected_palette = random.choice(modern_color_palettes)
        
        # Format the palette for the API
        formatted_palette = [
            {'name': f'Color {i+1}', 'hex': color} 
            for i, color in enumerate(selected_palette)
        ]
        
        return formatted_palette

    def extract_text_from_section(self, data, texts_list):
        """Recursively extract text from Elementor section data"""
        if isinstance(data, dict):
            # Check for text content in this item
            if 'text' in data and isinstance(data['text'], str) and len(data['text'].strip()) > 0:
                texts_list.append({
                    'text': data['text'].strip(),
                    'type': 'text'
                })
            elif 'title' in data and isinstance(data['title'], str) and len(data['title'].strip()) > 0:
                texts_list.append({
                    'text': data['title'].strip(),
                    'type': 'title'
                })
            elif 'heading' in data and isinstance(data['heading'], str) and len(data['heading'].strip()) > 0:
                texts_list.append({
                    'text': data['heading'].strip(),
                    'type': 'heading'
                })
            elif 'label' in data and isinstance(data['label'], str) and len(data['label'].strip()) > 0:
                texts_list.append({
                    'text': data['label'].strip(),
                    'type': 'label'
                })
            elif 'button_text' in data and isinstance(data['button_text'], str) and len(data['button_text'].strip()) > 0:
                texts_list.append({
                    'text': data['button_text'].strip(),
                    'type': 'button'
                })
                
            # Recursively check all values
            for value in data.values():
                self.extract_text_from_section(value, texts_list)
        elif isinstance(data, list):
            # Check all items in the list
            for item in data:
                self.extract_text_from_section(item, texts_list)
                
    def store_transformation_data(
        self,
        theme_id: str,
        text_transformations: List[Dict],
        colors: List[Dict],
        style_description: str = None
    ) -> bool:
        """
        Store transformation data in the Supabase database
        
        Args:
            theme_id: The theme ID
            text_transformations: List of text transformation dictionaries
            colors: List of color dictionaries
            style_description: Optional style description
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate theme_id as UUID
            try:
                valid_theme_id = str(uuid.UUID(theme_id))
            except (ValueError, TypeError):
                print(f"Error: Invalid theme_id format: {theme_id}")
                return False
            
            # Extract original texts for storage
            original_texts = []
            try:
                original_texts = [t.get('original', '') for t in text_transformations if t.get('original')]
            except Exception as e:
                print(f"Error extracting original texts: {e}")
                original_texts = []
            
            # Debug info about transformation data
            print(f"Debug - Storing transformation data:")
            print(f"  - Theme ID: {valid_theme_id}")
            print(f"  - Text transformations: {len(text_transformations)} items")
            print(f"  - Colors: {len(colors)} items")
            print(f"  - Original texts extracted: {len(original_texts)} items")
            
            # Check if text_transformations are properly structured
            for i, item in enumerate(text_transformations[:3]):  # Print first 3 for debugging
                print(f"  - Transformation {i}: {item.get('original', 'N/A')} -> {item.get('transformed', 'N/A')}")
            
            # Get Supabase credentials
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            
            if not supabase_url or not supabase_key:
                print("Error: Supabase credentials not configured")
                return False
            
            # Create Supabase client
            supabase = create_client(supabase_url, supabase_key)
            
            # Delete any existing transformation data for this theme
            try:
                supabase.table('transformation_data').delete().eq('theme_id', valid_theme_id).execute()
                print(f"Deleted existing transformation data for theme {valid_theme_id}")
            except Exception as e:
                print(f"Warning: Failed to delete existing transformation data: {e}")
                # Continue anyway
            
            # Create a new transformation record
            transformation_id = str(uuid.uuid4())
            
            # Prepare transformation record using only fields in the database schema
            transformation_record = {
                'id': transformation_id,
                'theme_id': valid_theme_id,
                'texts': json.dumps(original_texts),
                'colors': json.dumps(colors),
                'created_at': datetime.datetime.now().isoformat()
            }
            
            # Save debug file with transformation data
            debug_file = f"debug_transformation_{valid_theme_id}.json"
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'text_transformations': text_transformations,
                    'colors': colors,
                    'record': transformation_record
                }, f, indent=2)
            print(f"Saved debug transformation data to {debug_file}")
            
            # Insert the transformation record
            response = supabase.table('transformation_data').insert(transformation_record).execute()
            
            print(f"Stored transformation data with ID: {transformation_id}")
            print(f"Saved {len(text_transformations)} transformed texts and {len(colors)} colors")
            
            return True
            
        except Exception as e:
            print(f"Error storing transformation data: {e}")
            traceback.print_exc()
            return False

def main():
    # Create agent instance
    agent = ContentTransformationAgent()
    
    # Transform theme content
    theme_id = "ad8c2a68-e5ee-4a68-99be-f90e64ec52ea"  # Replace with actual theme ID
    style_description = "site for flowers with yellow colors"
    
    result = agent.transform_theme_content(theme_id, style_description)
    
    # Print results
    print("\nTransformation complete!")
    print(f"Transformed texts: {len(result['text_transformations'])}")
    print(f"New colors: {len(result['color_palette']['new_colors'])}")
    print(f"Output saved to: transformed_content_{theme_id}.json")

if __name__ == "__main__":
    main()
