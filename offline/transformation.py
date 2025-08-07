import datetime
import json
from openai import OpenAI
import re
from typing import Dict, List, Any, Tuple, Optional
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import random
import uuid
import traceback
import html
from color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping

def extract_business_info_from_gbp(gbp_data: str) -> Optional[Dict]:
    """
    Extract and format business information from a GBP object string.
    Returns None if no valid GBP data is found.
    """
    try:
        # Try to parse the GBP data
        if isinstance(gbp_data, str):
            gbp_object = json.loads(gbp_data)
        else:
            gbp_object = gbp_data
        
        # Handle both direct result format and full Google Places API response
        if "result" in gbp_object:
            result = gbp_object["result"]
        else:
            result = gbp_object
        
        # Extract business information
        business_info = {
            "business_name": result.get("name", ""),
            "address": result.get("formatted_address", ""),
            "phone": result.get("formatted_phone_number", ""),
            "international_phone": result.get("international_phone_number", ""),
            "website": result.get("website", ""),
            "business_status": result.get("business_status", ""),
            "rating": result.get("rating", 0),
            "total_reviews": result.get("user_ratings_total", 0),
            "place_id": result.get("place_id", ""),
            "url": result.get("url", ""),
            "vicinity": result.get("vicinity", ""),
            "geometry": result.get("geometry", {}),
            "types": result.get("types", []),
            "utc_offset": result.get("utc_offset", 0),
            "icon": result.get("icon", ""),
            "icon_background_color": result.get("icon_background_color", ""),
            "plus_code": result.get("plus_code", {}),
            "adr_address": result.get("adr_address", ""),
            "address_components": result.get("address_components", []),
            "html_attributions": gbp_object.get("html_attributions", []),
            "reference": result.get("reference", ""),
            "status": gbp_object.get("status", "")
        }
        
        # Process opening hours
        opening_hours = {}
        if result.get("opening_hours"):
            opening_hours = {
                "open_now": result["opening_hours"].get("open_now", False),
                "weekday_text": result["opening_hours"].get("weekday_text", []),
                "periods": result["opening_hours"].get("periods", [])
            }
        
        # Also check current_opening_hours if available
        if result.get("current_opening_hours"):
            opening_hours.update({
                "current_open_now": result["current_opening_hours"].get("open_now", False),
                "current_weekday_text": result["current_opening_hours"].get("weekday_text", []),
                "current_periods": result["current_opening_hours"].get("periods", [])
            })
        
        business_info["opening_hours"] = opening_hours
        
        # Process reviews
        reviews = []
        if result.get("reviews"):
            for review in result["reviews"]:
                if isinstance(review, dict):
                    review_info = {
                        "author_name": review.get("author_name", ""),
                        "author_url": review.get("author_url", ""),
                        "profile_photo_url": review.get("profile_photo_url", ""),
                        "rating": review.get("rating", 0),
                        "text": review.get("text", ""),
                        "time": review.get("time", 0),
                        "relative_time_description": review.get("relative_time_description", ""),
                        "language": review.get("language", "")
                    }
                    reviews.append(review_info)
        
        business_info["reviews"] = reviews
        
        # Process photos (just the metadata, not the actual images)
        photos = []
        if result.get("photos"):
            for photo in result["photos"]:
                if isinstance(photo, dict):
                    photo_info = {
                        "photo_reference": photo.get("photo_reference", ""),
                        "height": photo.get("height", 0),
                        "width": photo.get("width", 0),
                        "html_attributions": photo.get("html_attributions", [])
                    }
                    photos.append(photo_info)
        
        business_info["photos"] = photos
        
        return business_info
        
    except Exception as e:
        print(f"Error extracting business info from GBP data: {e}")
        return None

def format_business_info_for_prompt(business_info: Dict) -> str:
    """
    Format business information into a structured prompt for GPT.
    """
    if not business_info:
        return ""
    
    formatted_info = []
    
    # Basic business information
    if business_info.get("business_name"):
        formatted_info.append(f"Business Name: {business_info['business_name']}")
    
    if business_info.get("address"):
        formatted_info.append(f"Address: {business_info['address']}")
    
    if business_info.get("phone"):
        formatted_info.append(f"Phone: {business_info['phone']}")
    
    if business_info.get("international_phone"):
        formatted_info.append(f"International Phone: {business_info['international_phone']}")
    
    if business_info.get("website"):
        formatted_info.append(f"Website: {business_info['website']}")
    
    if business_info.get("rating"):
        formatted_info.append(f"Rating: {business_info['rating']} stars from {business_info.get('total_reviews', 0)} reviews")
    
    # Opening hours
    opening_hours = business_info.get("opening_hours", {})
    if opening_hours:
        weekday_text = opening_hours.get("weekday_text", [])
        current_weekday_text = opening_hours.get("current_weekday_text", [])
        
        if weekday_text:
            formatted_info.append("Opening Hours:")
            for day in weekday_text:
                formatted_info.append(f"  {day}")
        elif current_weekday_text:
            formatted_info.append("Opening Hours:")
            for day in current_weekday_text:
                formatted_info.append(f"  {day}")
    
    # Reviews
    reviews = business_info.get("reviews", [])
    if reviews:
        formatted_info.append("Customer Reviews:")
        for i, review in enumerate(reviews[:5]):  # Show first 5 reviews
            author = review.get("author_name", "Anonymous")
            text = review.get("text", "").strip()
            rating = review.get("rating", 0)
            time_desc = review.get("relative_time_description", "")
            
            if text:  # Only include reviews with text
                formatted_info.append(f"  {author} ({rating} stars, {time_desc}): '{text}'")
            else:
                formatted_info.append(f"  {author} ({rating} stars, {time_desc}): Rating only")
    
    # Business details
    if business_info.get("business_status"):
        formatted_info.append(f"Status: {business_info['business_status']}")
    
    if business_info.get("vicinity"):
        formatted_info.append(f"Location: {business_info['vicinity']}")
    
    return "\n".join(formatted_info)

class ContentTransformationAgent:
    def transform_posts(self, posts: List[Dict], style_description: str) -> List[Dict]:
        """
        For each post, transform both the title and content using GPT-4.1, and return a list of dicts with post_id, post_type, original_title, transformed_title, original, transformed.
        """
        # Check if style_description contains GBP data
        business_info = None
        business_prompt = ""
        final_style_description = style_description
        
        # Try to extract business information from the style description
        try:
            # Look for JSON-like content in the style description
            json_pattern = r'\{.*"result".*\}'
            json_matches = re.findall(json_pattern, style_description, re.DOTALL)
            
            if json_matches:
                # Found potential GBP data
                gbp_data = json_matches[0]
                business_info = extract_business_info_from_gbp(gbp_data)
                
                if business_info:
                    print(f"✅ Extracted business information for posts: {business_info.get('business_name', 'Unknown Business')}")
                    business_prompt = format_business_info_for_prompt(business_info)
                    
                    # Remove the JSON from the style description to avoid confusion
                    final_style_description = re.sub(json_pattern, '', style_description, flags=re.DOTALL).strip()
                    
                    # If no style description left, use a default one
                    if not final_style_description:
                        final_style_description = "modern professional business website"
                else:
                    print("⚠️  Found JSON in style description but couldn't extract business info for posts")
            else:
                print("ℹ️  No GBP data found in style description for posts, proceeding with normal transformation")
                
        except Exception as e:
            print(f"⚠️  Error processing style description for business info in posts: {e}")
        
        results = []
        for post in posts:
            post_id = post.get('wp_post_id')
            post_type = post.get('post_type', '')
            original_title = post.get('original_title', '')
            original_content = post.get('original_content', '')
            
            # Transform title
            if business_info and business_prompt:
                prompt_title = (
                    f"Transform this WordPress post title for: {final_style_description}\n"
                    f"Use this business information:\n{business_prompt}\n\n"
                    f"Original title: {original_title}\n"
                    "Return only the new, transformed title, making it relevant to this specific business and style. Do NOT return any unchanged text."
                )
            else:
                prompt_title = (
                    f"Transform this WordPress post title for: {final_style_description}\n"
                    f"Original title: {original_title}\n"
                    "Return only the new, transformed title, making it relevant to the style/business. Do NOT return any unchanged text."
                )
            
            try:
                response_title = self.client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": "You are a professional blog post title transformer for WordPress themes. Always transform the title to match the requested style/business."},
                        {"role": "user", "content": prompt_title}
                    ],
                    temperature=0.5,
                    max_tokens=128
                )
                transformed_title = response_title.choices[0].message.content.strip()
            except Exception as e:
                print(f"Error transforming post title for post_id {post_id}: {e}")
                transformed_title = original_title
            
            # Transform content
            transformed_content = self.transform_post_content_gpt(original_content, style_description)
            results.append({
                'post_id': post_id,
                'post_type': post_type,
                'original_title': original_title,
                'transformed_title': transformed_title,
                'original': original_content,
                'transformed': transformed_content
            })
        return results
    def transform_post_content_gpt(self, original_content: str, style_description: str) -> str:
        """
        Transform a WordPress post's HTML content using GPT-4.1, preserving all HTML structure and block comments.
        The output will have all visible text rewritten to match the requested style/business, but all HTML tags and structure will be preserved.
        """
        # Check if style_description contains GBP data
        business_info = None
        business_prompt = ""
        final_style_description = style_description
        
        # Try to extract business information from the style description
        try:
            # Look for JSON-like content in the style description
            json_pattern = r'\{.*"result".*\}'
            json_matches = re.findall(json_pattern, style_description, re.DOTALL)
            
            if json_matches:
                # Found potential GBP data
                gbp_data = json_matches[0]
                business_info = extract_business_info_from_gbp(gbp_data)
                
                if business_info:
                    print(f"✅ Extracted business information for post content: {business_info.get('business_name', 'Unknown Business')}")
                    business_prompt = format_business_info_for_prompt(business_info)
                    
                    # Remove the JSON from the style description to avoid confusion
                    final_style_description = re.sub(json_pattern, '', style_description, flags=re.DOTALL).strip()
                    
                    # If no style description left, use a default one
                    if not final_style_description:
                        final_style_description = "modern professional business website"
                else:
                    print("⚠️  Found JSON in style description but couldn't extract business info for post content")
            else:
                print("ℹ️  No GBP data found in style description for post content, proceeding with normal transformation")
                
        except Exception as e:
            print(f"⚠️  Error processing style description for business info in post content: {e}")
        
        # Prepare the system message based on whether we have business info
        if business_info and business_prompt:
            system_content = (
                "You are a professional WordPress post transformer. "
                "IMPORTANT: The following business information must be preserved exactly as provided and used in the content:\n\n"
                f"{business_prompt}\n\n"
                "When transforming content, use this business information to create relevant, accurate content. "
                "For reviews, use the exact reviewer names, ratings, and text provided. "
                "For business details, use the exact name, address, phone, website, and hours provided. "
                "Always transform all visible text, including inside HTML and block comments, but preserve the HTML structure and all tags. "
                "Never return unchanged text."
            )
        else:
            system_content = (
                "You are a professional WordPress post transformer. "
                "Always transform all visible text, including inside HTML and block comments, but preserve the HTML structure and all tags. "
                "Never return unchanged text."
            )
        
        prompt = (
            f"Transform the following WordPress post HTML content for: {final_style_description}\n"
            f"Original HTML content (including all block comments and tags):\n{original_content}\n"
            "Return only the new, transformed HTML content, keeping the structure and blocks, but making all text relevant to the style/business. Do NOT return any unchanged text."
        )
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2048
            )
            new_content = response.choices[0].message.content.strip()
            return new_content
        except Exception as e:
            print(f"Error transforming post content with GPT-4.1: {e}")
            return original_content
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

    def transform_theme_content(self, theme_id: str, style_description: str, filtered_pages: List[Dict] = None, filtered_sections: List[Dict] = None, extracted_posts: List[Dict] = None) -> Dict:
        """Transform theme content based on style description, including posts if provided."""
        try:
            if not filtered_pages and not filtered_sections:
                result = self.supabase.table('transformation_data')\
                    .select('*')\
                    .eq('theme_id', theme_id)\
                    .execute()
                if not result.data:
                    transformation_data = self._generate_new_transformation_data(theme_id, style_description)
                else:
                    transformation_data = result.data[0]
                texts_to_transform = transformation_data.get('texts', [])
                colors_to_transform = transformation_data.get('colors', [])
                # Use extracted_posts if provided, else fallback to DB
                if extracted_posts is not None:
                    post_transformations = self.transform_posts(extracted_posts, style_description)
                else:
                    posts_result = self.supabase.table('pages').select('*').eq('theme_id', theme_id).limit(1000).execute()
                    post_transformations = []
                    if posts_result.data:
                        # Fallback: try to transform posts from DB if available
                        for p in posts_result.data:
                            post_id = p.get('wp_post_id') or p['id']
                            post_type = p.get('post_type', '')
                            original_title = p.get('original_title', '')
                            original_content = p.get('original_content', '')
                            if post_type == 'post' and original_content:
                                transformed = self.transform_post_content_gpt(original_content, style_description)
                                post_transformations.append({
                                    'post_id': post_id,
                                    'post_type': post_type,
                                    'original_title': original_title,
                                    'transformed_title': original_title,
                                    'original': original_content,
                                    'transformed': transformed
                                })
            else:
                texts_to_transform = []
                colors_to_transform = []
                post_transformations = []
                for page in filtered_pages:
                    if 'content' in page:
                        texts_to_transform.extend(self._extract_texts_from_content(page['content']))
                        colors_to_transform.extend(self._extract_colors_from_content(page['content']))
                        if page.get('category') == 'post':
                            transformed = self.transform_post_content_gpt(page['content'], style_description)
                            post_transformations.append({
                                'post_id': page.get('id'),
                                'original': page['content'],
                                'transformed': transformed
                            })
                for section in filtered_sections:
                    if 'content' in section:
                        try:
                            section_data = json.loads(section['content'])
                            texts_from_section = []
                            self.extract_text_from_section(section_data, texts_from_section)
                            texts_to_transform.extend([t['text'] for t in texts_from_section])
                        except:
                            texts_to_transform.extend(self._extract_texts_from_content(section['content']))
                        colors_to_transform.extend(self._extract_colors_from_content(section['content']))
                texts_to_transform = list(dict.fromkeys(texts_to_transform))
                colors_to_transform = list(dict.fromkeys(colors_to_transform))
            print(f"Loaded {len(texts_to_transform)} texts and {len(colors_to_transform)} colors")
            transformed_content = self._generate_transformed_content(texts_to_transform, colors_to_transform, style_description)
            transformed_colors = self._transform_colors(colors_to_transform, style_description)
            return {
                'text_transformations': transformed_content.get('text_transformations', []),
                'color_palette': transformed_colors.get('color_palette', {}),
                'transformation_notes': transformed_colors.get('transformation_notes', ''),
                'style_description': style_description,
                'full_palette': transformed_colors.get('full_palette', {}),
                'theme_id': theme_id,
                'post_transformations': post_transformations,
            }
        except Exception as e:
            print(f"An error occurred in transform_theme_content: {e}")
            import traceback
            traceback.print_exc()
            return {
                'text_transformations': [],
                'color_palette': {},
                'transformation_notes': '',
                'style_description': style_description,
                'full_palette': {},
                'theme_id': theme_id,
                'post_transformations': [],
            }
    def _transform_post_content(self, content: str, style_description: str) -> str:
        """Transform a single post's content, preserving all HTML and block comments."""
        # Pass the full HTML content (including block comments and tags) to the transformer
        prompt = (
            f"Transform this WordPress post content for: {style_description}\n"
            f"Original HTML content (including all block comments and tags):\n{content}\n"
            "Return only the new, transformed HTML content, keeping the structure and blocks, but making all text relevant to the style/business. Do NOT return any unchanged text."
        )
        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "You are a professional blog post transformer for WordPress themes. Always transform all text, including inside HTML and block comments, but preserve the HTML structure."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2048
            )
            new_content = response.choices[0].message.content.strip()
            return new_content
        except Exception as e:
            print(f"Error transforming post content: {e}")
            return content
            
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
        """Generate new transformation data by extracting ALL text and colors from database, including duplicates and lorem ipsum."""
        texts = []
        colors = []
        try:
            # Fetch sections
            sections_result = self.supabase.table('sections') \
                .select('*') \
                .eq('theme_id', theme_id) \
                .limit(1000) \
                .execute()
            if sections_result.data:
                for section in sections_result.data:
                    section_content = section.get('content')
                    if section_content:
                        try:
                            section_data = json.loads(section_content)
                            texts_from_section = []
                            self.extract_text_from_section(section_data, texts_from_section, include_lorem=True)
                            texts.extend([t['text'] for t in texts_from_section])
                        except Exception as e:
                            print(f"Error parsing section content: {e}")
        except Exception as e:
            print(f"Error fetching sections: {e}")
        # Do NOT deduplicate or filter out lorem ipsum or short texts
        print(f"Found {len(texts)} total texts from sections (including duplicates and lorem ipsum)")
        # Default colors if none found
        default_colors = ['#2989CE', '#16202F', '#E22E40', '#FFFFFF', '#757A81']
        colors = colors or default_colors
        return {
            'theme_id': theme_id,
            'texts': texts,
            'colors': colors
        }

    def _generate_transformed_content(self, texts: List[str], colors: List[str], style_description: str) -> Dict:
        """Generate transformed content for texts and colors, transforming EVERY text (including duplicates and lorem ipsum, in any language)."""
        def is_lorem(text):
            text_lower = text.lower()
            return (
                'lorem ipsum' in text_lower or
                'لوريم' in text_lower or
                'إيبسوم' in text_lower or
                'دولور' in text_lower or
                'سيت أميت' in text_lower or
                'dummy text' in text_lower
            )
        
        # Check if style_description contains GBP data
        business_info = None
        business_prompt = ""
        final_style_description = style_description
        
        # Try to extract business information from the style description
        try:
            # Look for JSON-like content in the style description
            json_pattern = r'\{.*"result".*\}'
            json_matches = re.findall(json_pattern, style_description, re.DOTALL)
            
            if json_matches:
                # Found potential GBP data
                gbp_data = json_matches[0]
                business_info = extract_business_info_from_gbp(gbp_data)
                
                if business_info:
                    print(f"✅ Extracted business information for: {business_info.get('business_name', 'Unknown Business')}")
                    business_prompt = format_business_info_for_prompt(business_info)
                    
                    # Remove the JSON from the style description to avoid confusion
                    final_style_description = re.sub(json_pattern, '', style_description, flags=re.DOTALL).strip()
                    
                    # If no style description left, use a default one
                    if not final_style_description:
                        final_style_description = "modern professional business website"
                    
                    print(f"📝 Business prompt prepared with {len(business_info.get('reviews', []))} reviews and business details")
                else:
                    print("⚠️  Found JSON in style description but couldn't extract business info")
            else:
                print("ℹ️  No GBP data found in style description, proceeding with normal transformation")
                
        except Exception as e:
            print(f"⚠️  Error processing style description for business info: {e}")
        
        try:
            valid_texts = [text for text in texts if text and len(text.strip()) > 0]
            batch_size = 10
            transformed_pairs = []
            
            for i in range(0, len(valid_texts), batch_size):
                batch = valid_texts[i:i + batch_size]
                
                # Prepare the system message based on whether we have business info
                if business_info and business_prompt:
                    system_content = (
                        "You are a professional content transformer for a WordPress theme. "
                        "IMPORTANT: The following business information must be preserved exactly as provided and used in the content:\n\n"
                        f"{business_prompt}\n\n"
                        "When transforming content, use this business information to create relevant, accurate content. "
                        "For reviews, use the exact reviewer names, ratings, and text provided. "
                        "For business details, use the exact name, address, phone, website, and hours provided. "
                        "Transform each text to match the requested style while:\n"
                        "1. Always generate new, meaningful content that incorporates the provided business information.\n"
                        "2. If the text is lorem ipsum, placeholder, or dummy text, replace it with real content about this specific business.\n"
                        "3. Preserve the core meaning and key information if present.\n"
                        "4. Maintain similar length and structure.\n"
                        "5. Make content relevant to this specific business and the requested style.\n"
                        "6. Keep function words (buttons, labels, etc.) concise and action-oriented.\n"
                        "7. Prevent any special characters from being used in the transformed text.\n"
                        "Format: For each text return exactly:\nORIGINAL: [original text]\nNEW: [transformed text]"
                    )
                else:
                    system_content = (
                        "You are a professional content transformer for a WordPress theme. "
                        "Transform each text to match the requested style while:\n"
                        "1. Always generate a new, meaningful, and relevant text for every input, never returning any text unchanged (even for lorem ipsum, dummy, or placeholder text in any language, including Arabic).\n"
                        "2. If the text is lorem ipsum, placeholder, or dummy text (in any language), always replace it with real, relevant content for the requested style and language.\n"
                        "3. Preserve the core meaning and key information if present.\n"
                        "4. Maintain similar length and structure.\n"
                        "5. Make content relevant to the requested style/business type.\n"
                        "6. Keep function words (buttons, labels, etc.) concise and action-oriented.\n"
                        "7. Prevent any special characters from being used in the transformed text.\n"
                        "Format: For each text return exactly:\nORIGINAL: [original text]\nNEW: [transformed text]"
                    )
                
                messages = [
                    {
                        "role": "system",
                        "content": system_content
                    },
                    {
                        "role": "user",
                        "content": f"""Transform these texts for: {final_style_description}\n\nOriginal texts:\n{json.dumps(batch, indent=2)}\n\nReturn each transformation in the format:\nORIGINAL: [text]\nNEW: [transformed text]"""
                    }
                ]
                
                try:
                    response = self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=messages,
                        temperature=0.5,
                        max_tokens=2048
                    )
                    response_text = response.choices[0].message.content
                    pairs = re.split(r'ORIGINAL:', response_text)[1:]
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
                    for text in batch:
                        transformed_pairs.append({
                            "original": text,
                            "transformed": text
                        })
            
            # Post-process: re-transform any text that still looks like lorem/placeholder
            for pair in transformed_pairs:
                if is_lorem(pair['transformed']):
                    print(f"Re-transforming placeholder/lorem text: {pair['transformed']}")
                    # Re-transform with a direct prompt
                    try:
                        re_transform_prompt = "Replace this placeholder or lorem ipsum text (in any language) with real, relevant content for: " + final_style_description
                        if business_info:
                            re_transform_prompt += f"\n\nUse this business information:\n{business_prompt}"
                        
                        messages = [
                            {"role": "system", "content": re_transform_prompt},
                            {"role": "user", "content": pair['transformed']}
                        ]
                        response = self.client.chat.completions.create(
                            model="gpt-4.1",
                            messages=messages,
                            temperature=0.4,
                            max_tokens=256
                        )
                        new_text = response.choices[0].message.content.strip()
                        if not is_lorem(new_text):
                            pair['transformed'] = new_text
                    except Exception as e:
                        print(f"Error in re-transforming placeholder: {e}")
            
            transformed_colors = self._transform_colors(colors, final_style_description)
            return {
                "text_transformations": transformed_pairs,
                "color_palette": transformed_colors.get('color_palette', {}),
                "business_info": business_info
            }
        except Exception as e:
            print(f"Error generating transformed content: {e}")
            return {
                "text_transformations": [{"original": t, "transformed": t} for t in texts],
                "color_palette": {"original_colors": colors, "new_colors": colors},
                "business_info": business_info
            }

    def _transform_colors(self, colors: List[str], style_description: str) -> Dict:
        """Transform colors according to style description using color theory instead of GPT"""
        try:
            # Remove duplicates while preserving order
            unique_colors = []
            [unique_colors.append(c) for c in colors if c not in unique_colors]
            
            print(f"Transforming {len(unique_colors)} colors based on style description: {style_description}")
            
            # Create color mapping using our new color utilities
            color_map, palette = create_color_mapping(unique_colors, style_description)
            
            # Format the result in the expected structure for compatibility
            new_colors = [color_map.get(color, color) for color in unique_colors]
            
            # Generate notes about the color palette
            notes = f"Color palette generated based on '{style_description}'. "
            notes += f"Primary color extracted and used to generate a harmonious palette with "
            notes += f"complementary, analogous, and monochromatic variations. "
            notes += f"Palette includes {len(palette)} colors mapped to appropriate Elementor elements."
            
            return {
                "color_palette": {
                    "original_colors": unique_colors,
                    "new_colors": new_colors
                },
                "transformation_notes": notes,
                "full_palette": palette  # Include the full palette for reference
            }
            
        except Exception as e:
            print(f"Error transforming colors: {e}")
            traceback.print_exc()
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

    def extract_text_from_section(self, data, texts_list, include_lorem=False):
        """Recursively extract text from Elementor section data, including all lorem ipsum and duplicates if include_lorem=True."""
        if isinstance(data, dict):
            # Check for text content in this item
            for key in ['text', 'title', 'heading', 'label', 'button_text', 'editor', 'subtitle', 'description', 'content', 'tab_title', 'address']:
                if key in data and isinstance(data[key], str) and len(data[key].strip()) > 0:
                    value = data[key].strip()
                    if include_lorem or not self._is_lorem(value):
                        texts_list.append({'text': value, 'type': key})
            # Recursively check all values
            for value in data.values():
                self.extract_text_from_section(value, texts_list, include_lorem=include_lorem)
        elif isinstance(data, list):
            for item in data:
                self.extract_text_from_section(item, texts_list, include_lorem=include_lorem)

    def _is_lorem(self, text: str) -> bool:
        """Detect if text is lorem ipsum in any language (basic check)."""
        text_lower = text.lower()
        return (
            'lorem ipsum' in text_lower or
            'لوريم' in text_lower or
            'إيبسوم' in text_lower or
            'دولور' in text_lower or
            'سيت أميت' in text_lower or
            'dummy text' in text_lower
        )

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

    def _replace_texts_in_elementor_data(self, elementor_data: Any, text_map: Dict[str, str]) -> Any:
        """Recursively replace every original text in elementor_data with its transformed version, including all duplicates and lorem ipsum."""
        if isinstance(elementor_data, dict):
            for key, value in elementor_data.items():
                if isinstance(value, str) and value in text_map:
                    elementor_data[key] = text_map[value]
                elif isinstance(value, (dict, list)):
                    elementor_data[key] = self._replace_texts_in_elementor_data(value, text_map)
            return elementor_data
        elif isinstance(elementor_data, list):
            return [self._replace_texts_in_elementor_data(item, text_map) for item in elementor_data]
        else:
            return elementor_data

    def apply_text_transformations_to_theme(self, theme_id: str, text_transformations: List[Dict]) -> None:
        """Apply all text transformations to every section in the theme, replacing every occurrence (including duplicates and lorem ipsum)."""
        # Build a mapping from original to transformed
        text_map = {t['original']: t['transformed'] for t in text_transformations if t.get('original') and t.get('transformed')}
        # Fetch all sections for this theme
        sections_result = self.supabase.table('sections').select('*').eq('theme_id', theme_id).limit(1000).execute()
        if sections_result.data:
            for section in sections_result.data:
                section_id = section['id']
                content = section.get('content')
                if content:
                    try:
                        section_data = json.loads(content)
                        updated_section_data = self._replace_texts_in_elementor_data(section_data, text_map)
                        # Update the section in the database
                        self.supabase.table('sections').update({'content': json.dumps(updated_section_data)}).eq('id', section_id).execute()
                    except Exception as e:
                        print(f"Error updating section {section_id}: {e}")

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
