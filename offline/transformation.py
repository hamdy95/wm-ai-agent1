import datetime
import json
from openai import OpenAI
import re
from typing import Dict, List, Any
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import random

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

    def transform_theme_content(self, theme_id: str, style_description: str) -> Dict:
        """Transform theme content based on style description"""
        try:
            # Fetch transformation data for the theme
            result = self.supabase.table('transformation_data')\
                .select('*')\
                .eq('theme_id', theme_id)\
                .execute()
                
            if not result.data:
                # If no transformation data exists, generate new data
                transformation_data = self._generate_new_transformation_data(theme_id, style_description)
            else:
                transformation_data = result.data[0]
                
            print(f"Loaded {len(transformation_data['texts'])} texts and {len(transformation_data['colors'])} colors")

            # Transform texts in batches
            batch_size = 5
            transformed_texts = []
            for i in range(0, len(transformation_data['texts']), batch_size):
                batch_texts = transformation_data['texts'][i:i + batch_size]
                batch_result = self._generate_transformed_content(
                    batch_texts,
                    transformation_data['colors'],
                    style_description
                )
                transformed_texts.extend(batch_result['text_transformations'])

            # Generate new color palette
            color_result = self._generate_color_palette(
                transformation_data['colors'],
                style_description
            )

            # Save transformed content to file
            output_data = {
                'text_transformations': transformed_texts,
                'color_palette': color_result['color_palette'],
                'transformation_notes': color_result.get('transformation_notes', '')
            }

            # Write debug info to help diagnose issues
            debug_path = f"debug_transformed_content_{theme_id}.json"
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'input': {
                        'texts': transformation_data['texts'],
                        'colors': transformation_data['colors']
                    },
                    'output': output_data
                }, f, indent=2, ensure_ascii=False)
            print(f"Saved debug transformation info to {debug_path}")

            # Save to file
            output_path = f"transformed_content_{theme_id}.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            return output_data

        except Exception as e:
            print(f"Error in transform_theme_content: {e}")
            raise
            
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
        """Generate transformed content for a batch of texts"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are a WordPress theme content transformer. Transform each text to match the requested style while:
                    1. Preserving the core meaning and key information
                    2. Maintaining appropriate length and structure
                    3. Ensuring professional and coherent output
                    4. Never returning text unchanged unless explicitly requested
                    5. Make the content length close to the given not much bigger or smaller
                    6. You are taking the original text and this for the content for last desing needs your mission os to transform this content to new one based on user needs
                    Format each transformation exactly as: 'ORIGINAL: [text] 
                    NEW: [transformed text]'"""
                },
                {
                    "role": "user",
                    "content": f"""Transform these WordPress theme texts to match this user needs: {style_description}
                    so you change the each original text to new content based on user style
 
                    Original texts:
                    {json.dumps(texts, indent=2)}
 
                    Required format for each text:
                    ORIGINAL: [original text]
                    NEW: [transformed text]"""
                }
            ]

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=messages,
                temperature=0.7,
                max_tokens=4096
            )

            response_text = response.choices[0].message.content
            
            # Parse the response to extract the transformed texts
            transformed_pairs = []
            transformations = re.split(r'ORIGINAL:', response_text)[1:]
            
            for trans in transformations:
                parts = trans.split('NEW:', 1)
                if len(parts) == 2:
                    original = parts[0].strip()
                    transformed = parts[1].strip()
                    
                    # Clean up any extra formatting
                    transformed = re.sub(r'ORIGINAL:.*', '', transformed).strip()
                    transformed = re.sub(r'===.*===', '', transformed).strip()
                    
                    # Store both original and transformed text as a dictionary
                    transformed_pairs.append({
                        "original": original,
                        "transformed": transformed
                    })
            
            # Ensure we have at least some transformed texts
            if len(transformed_pairs) < len(texts):
                print(f"Warning: Missing transformations. Got {len(transformed_pairs)}, expected {len(texts)}")
                # Add the original texts for any missing transformations
                for i in range(len(transformed_pairs), len(texts)):
                    transformed_pairs.append({
                        "original": texts[i],
                        "transformed": texts[i]
                    })
            
            return {"text_transformations": transformed_pairs}

        except Exception as e:
            print(f"Error generating transformed content: {e}")
            return {"text_transformations": [], "error": f"Error: {str(e)}"}

    def _generate_color_palette(self, colors: List[str], style_description: str) -> Dict:
        """Generate a new color palette based on style description"""
        try:
            # Remove duplicates while preserving order
            unique_colors = []
            for color in colors:
                if isinstance(color, str) and color not in unique_colors:
                    unique_colors.append(color)
            
            # If we have too many colors, take only the first 10
            if len(unique_colors) > 10:
                unique_colors = unique_colors[:10]
            
            messages = [{
                "role": "system",
                "content": """You are a color palette generator for WordPress themes.
                Generate new hex colors that match the requested style.
                Always provide completely different colors than the original.
                Return ONLY the new colors in the exact same format as the input, preserving case.
                """
            },
            {
                "role": "user",
                "content": f"""
                Generate a new color palette matching this style: {style_description}
                Replace these colors with new ones that match the style:
                {json.dumps(unique_colors, indent=2)}
                
                Return only the list of new colors in the same format, maintaining letter case.
                Example format:
                === COLOR PALETTE ===
                NEW COLORS: [list of new hex codes]
                === NOTES ===
                [Explain your color choices]
                """
            }]

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=messages,
                temperature=0.7,
                max_tokens=4096
            )

            response_text = response.choices[0].message.content
            
            # Extract the color palette
            color_section = re.search(r'NEW COLORS:(.+?)(?===|$)', response_text, re.DOTALL)
            new_colors = []
            if color_section:
                new_colors = re.findall(r'#[0-9a-fA-F]{3,6}', color_section.group(1))
            
            # Extract notes
            notes_section = re.search(r'=== NOTES ===(.+?)(?===|$)', response_text, re.DOTALL)
            transformation_notes = notes_section.group(1).strip() if notes_section else ""
            
            # Ensure we have enough colors (use modulo cycling if needed)
            while len(new_colors) < len(unique_colors):
                new_colors.append(new_colors[len(new_colors) % len(new_colors)] if new_colors else "#000000")
            
            # Trim to match the original length
            new_colors = new_colors[:len(unique_colors)]
            
            return {
                "color_palette": {
                    "original_colors": unique_colors,
                    "new_colors": new_colors
                },
                "transformation_notes": transformation_notes or "Color transformation complete"
            }

        except Exception as e:
            print(f"Error generating color palette: {e}")
            # Return a minimal color palette as fallback
            return {
                "color_palette": {
                    "original_colors": colors[:min(10, len(colors))],
                    "new_colors": colors[:min(10, len(colors))]
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
                
    def transform_text(self, text: str, style_description: str) -> str:
        """Transform a single text element according to the style description"""
        # Skip very short text or numbers-only
        if len(text) < 5 or text.isdigit():
            return text
            
        try:
            # Prepare a prompt for high-quality transformation
            prompt = [
                {"role": "system", "content": f"You are a professional copywriter specializing in transforming text according to style guidelines. Transform the following text to match this style: {style_description}. Keep the same general meaning but adjust the wording and tone to fit the style."},
                {"role": "user", "content": f"Original text: \"{text}\"\nTransformed text:"}
            ]
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=prompt,
                temperature=0.7,
                max_tokens=4096
            )
            
            # Extract the transformed text
            transformed_text = response.choices[0].message.content.strip()
            
            # Remove quotes if they exist
            if transformed_text.startswith('"') and transformed_text.endswith('"'):
                transformed_text = transformed_text[1:-1]
                
            return transformed_text
            
        except Exception as e:
            print(f"Error transforming text: {e}")
            return text  # Return original if transformation fails

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