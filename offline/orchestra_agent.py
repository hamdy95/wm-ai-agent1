from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form, Depends, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Union
import xml.etree.ElementTree as ET
import uuid
import shutil
import os
import sys
from datetime import datetime
import json
from supabase import create_client
import re
import time
import glob
import random
import traceback
from dotenv import load_dotenv
from replace import replace_text_and_colors, replace_with_images
import logging

# Create FastAPI app instance at module level
app = FastAPI(
    title="WordPress Theme Transformer API",
    description="API for transforming WordPress themes with Elementor",
    version="1.0.0"
)

# Configure CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Simple agent-aware logger for terminal visibility
def agent_log(agent: str, message: str) -> None:
    try:
        ts = datetime.utcnow().isoformat()
        line = f"[{ts}] [{agent}] {message}"
        logging.info(line)
    finally:
        # Always print to ensure visibility in terminal
        print(line)

# Handle imports differently based on how script is run
try:
    # When imported as a module
    from offline.agentoff import FixedElementorExtractor
    from offline.transformation import ContentTransformationAgent
    from offline.onepage_agent import OnePageSiteGenerator
    from offline.multipage_agent import MultiPageSiteGenerator
    from offline.evaluator_agent import SectionEvaluator
    from offline.color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping, generate_color_palette_with_gpt4o
    from offline.image_agent import get_image_for_element as get_image_suggestion
except ImportError:
    # When run directly
    from agentoff import FixedElementorExtractor
    from transformation import ContentTransformationAgent
    from onepage_agent import OnePageSiteGenerator
    from multipage_agent import MultiPageSiteGenerator
    from evaluator_agent import SectionEvaluator
    from color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping, generate_color_palette_with_gpt4o
    try:
        from image_agent import get_image_for_element as get_image_suggestion
    except ImportError:
        get_image_suggestion = None

# Define response models
class TransformationResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    message: Optional[str] = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    output_url: Optional[str] = None
    error: Optional[str] = None

# Google Places OnePage request model - simplified to one parameter
class GoogleOnePageRequest(BaseModel):
    google_data: dict = Field(..., description="Full Google Places API result JSON with optional style_description and replace_images")

# New AI-native one page request model
class AIOnePageRequest(BaseModel):
    style_description: str = Field(..., description="Overall brand/style description to plan and generate sections")
    google_data: Optional[dict] = Field(None, description="Optional Google Places/GBP data; if provided, business info is preserved exactly")
    replace_images: Optional[bool] = False

# Google Business Profile object model
class GoogleBusinessProfile(BaseModel):
    name: Optional[str] = None
    formatted_address: Optional[str] = None
    formatted_phone_number: Optional[str] = None
    website: Optional[str] = None
    business_status: Optional[str] = None
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    opening_hours: Optional[dict] = None
    photos: Optional[List[dict]] = None
    reviews: Optional[List[dict]] = None
    geometry: Optional[dict] = None
    types: Optional[List[str]] = None
    vicinity: Optional[str] = None
    international_phone_number: Optional[str] = None
    place_id: Optional[str] = None
    url: Optional[str] = None
    utc_offset: Optional[int] = None
    icon: Optional[str] = None
    icon_background_color: Optional[str] = None
    icon_mask_base_uri: Optional[str] = None
    plus_code: Optional[dict] = None
    adr_address: Optional[str] = None
    address_components: Optional[List[dict]] = None
    current_opening_hours: Optional[dict] = None
    html_attributions: Optional[List[str]] = None
    reference: Optional[str] = None
    status: Optional[str] = None

# Updated request models with google_data instead of gbp_object
class StyleDescription(BaseModel):
    description: str
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class SiteGenerationRequest(BaseModel):
    query: str
    style_description: Optional[str] = "modern professional style with clean design"
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class ThemeIdTransformation(BaseModel):
    theme_id: str
    style_description: str
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class RecreateThemeRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class EvaluateSectionsRequest(BaseModel):
    theme_id: str
    detailed_analysis: Optional[bool] = True
    google_data: Optional[dict] = None

# New request model for color mapping API
class ColorMappingRequest(BaseModel):
    job_id: str

# New request model for page information API
class PageInfoRequest(BaseModel):
    job_id: str

# Add CDATA class for XML
class CDATA:
    """Helper class to handle CDATA sections in XML"""
    def __init__(self, text):
        self.text = text
        
    def __str__(self):
        return self.text  # Return plain text instead of CDATA

# Remove the problematic XML serialization override
# ET._original_serialize_xml = ET._serialize_xml

# def _serialize_xml(write, elem, qnames, namespaces, short_empty_elements=True, **kwargs):
#     if elem.text is not None and elem.text.__class__.__name__ == "CDATA":
#         write("<{}".format(qnames[elem.tag]))
#         items = list(elem.items())
#         if items:
#             items.sort()
#             for name, value in items:
#                 write(' {}="{}"'.format(qnames[name], xml_escape(value)))
#         write(">")
#         write(str(elem.text))
#         write("</{}>".format(qnames[elem.tag]))
#         if elem.tail:
#             write(xml_escape(elem.tail))
#     else:
#         return ET._original_serialize_xml(write, elem, qnames, namespaces, short_empty_elements, **kwargs)
        
# ET._serialize_xml = _serialize_xml

def xml_escape(text):
    if not text:
        return text
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("\"", "&quot;")
    text = text.replace("'", "&apos;")
    return text

# Define the Orchestrator
class ThemeTransformerOrchestrator:
    def __init__(self):
        """Initialize the orchestrator"""
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.jobs: Dict[str, Dict] = {}
        
        # Initialize agents
        try:
            # When imported as a module
            from offline.agentoff import FixedElementorExtractor
            from offline.transformation import ContentTransformationAgent
            from offline.onepage_agent import OnePageSiteGenerator
            from offline.multipage_agent import MultiPageSiteGenerator
            from offline.evaluator_agent import SectionEvaluator
        except ImportError:
            # When run directly
            from agentoff import FixedElementorExtractor
            from transformation import ContentTransformationAgent
            from onepage_agent import OnePageSiteGenerator
            from multipage_agent import MultiPageSiteGenerator
            from evaluator_agent import SectionEvaluator
        
        self.extraction_agent = FixedElementorExtractor()
        self.transformation_agent = ContentTransformationAgent()
        self.onepage_generator = OnePageSiteGenerator()
        self.multipage_generator = MultiPageSiteGenerator()
        self.section_evaluator = SectionEvaluator()
        
        # Create work directories
        for dir_name in ["input", "processing", "output"]:
            dir_path = os.path.join(self.base_dir, dir_name)
            os.makedirs(dir_path, exist_ok=True)
            
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # --- AI-native one-page generator helpers ---
    def _ai_strip_code_fences(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'^```(json)?', '', text.strip())
        text = re.sub(r'```$', '', text.strip())
        return text.strip()

    def _ai_parse_json(self, text: str) -> Any:
        try:
            clean = self._ai_strip_code_fences(text)
            return json.loads(clean)
        except Exception:
            # Try to extract JSON object via regex
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            # Try to extract list as well
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            raise ValueError("Failed to parse JSON from AI response")

    def _ai_get_text(self, resp: Any) -> str:
        # Defensive extraction of text from Gemini SDK response
        try:
            txt = getattr(resp, 'text', None)
            if txt:
                return txt
        except Exception:
            pass
        try:
            candidates = getattr(resp, 'candidates', None)
            if candidates:
                for cand in candidates:
                    try:
                        content = getattr(cand, 'content', None)
                        parts = getattr(content, 'parts', None) if content else None
                        if parts:
                            combined = ''.join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
                            if combined.strip():
                                return combined
                    except Exception:
                        continue
        except Exception:
            pass
        # Fallback to string form
        return str(resp)

    def _summarize_business_info(self, business_info: Optional[dict]) -> Optional[dict]:
        if not business_info:
            return None
        summary = {
            'business_name': business_info.get('business_name', ''),
            'address': business_info.get('address', ''),
            'phone': business_info.get('phone', ''),
            'website': business_info.get('website', ''),
            'rating': business_info.get('rating', 0),
            'total_reviews': business_info.get('total_reviews', 0),
            'opening_hours': {
                'weekday_text': (business_info.get('opening_hours', {}) or {}).get('weekday_text', [])[:7]
            }
        }
        # Limit reviews/photos to keep prompt small
        reviews = business_info.get('reviews', []) or []
        limited_reviews = []
        for r in reviews[:3]:
            limited_reviews.append({
                'author_name': r.get('author_name', ''),
                'rating': r.get('rating', 0),
                'text': (r.get('text', '') or '')[:400]
            })
        photos = business_info.get('photos', []) or []
        limited_photos = []
        for p in photos[:3]:
            ref = p.get('photo_reference') or ''
            if ref:
                limited_photos.append({'photo_reference': ref[:80]})
        if limited_reviews:
            summary['reviews'] = limited_reviews
        if limited_photos:
            summary['photos'] = limited_photos
        return summary

    def _ai_generate_plan(self, style_description: str, business_info: Optional[dict]) -> List[dict]:
        # Lazy import Gemini
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("google-generativeai is not installed. Please `pip install google-generativeai`.")
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-pro")

        preserve = "" if not business_info else (
            "Preserve exactly (do not rewrite): business name, address, phone, website, hours and reviews. Use them verbatim in content.\n"
        )
        summarized = self._summarize_business_info(business_info)
        user_prompt = f"""
You are a senior web UX planner. Plan an Elementor one-page site from this style description:
"""
        user_prompt += style_description + "\n\n"
        if summarized:
            user_prompt += "Business information to preserve and use:\n" + json.dumps(summarized, ensure_ascii=False, indent=2) + "\n\n"
        user_prompt += (
            "Return ONLY valid JSON (no commentary). Schema:\n"
            "{\n  \"sections\": [\n    {\n      \"id\": \"string\",\n      \"type\": \"hero|about|services|testimonials|faq|contact|cta|portfolio|team|features|footer\",\n      \"goal\": \"short purpose\",\n      \"components\": [\"heading\", \"subheading\", \"text\", \"button\", \"image\", \"list\"],\n      \"image_context\": \"what to show if an image is needed\",\n      \"tone\": \"tone of voice\"\n    }\n  ]\n}\n"
            f"{preserve}Plan 5-8 sections appropriate for the brief."
        )
        agent_log('Planner', 'Sending planning prompt to Gemini')
        resp = model.generate_content(user_prompt)
        text = self._ai_get_text(resp)
        agent_log('Planner', f'Received plan text length: {len(text)}')
        try:
            _preview = (text or '')[:300].replace('\n', ' ')
        except Exception:
            _preview = ''
        agent_log('Planner', f'Plan preview: {_preview}...')
        plan = self._ai_parse_json(text)
        if not isinstance(plan, dict) or 'sections' not in plan:
            raise ValueError("AI plan did not include 'sections'")
        return plan['sections']

    def _ai_generate_section_data(self, section_spec: dict, style_description: str, business_info: Optional[dict]) -> dict:
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("google-generativeai is not installed. Please `pip install google-generativeai`.")
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-pro")

        preserve = "" if not business_info else (
            "Preserve exactly: business name, address, phone, website, opening hours and reviews text/names/ratings.\n"
        )
        schema_hint = (
            "Return ONLY valid JSON with this exact structure for Elementor section_data (no commentary):\n"
            "{\n  \"id\": \"string\",\n  \"elType\": \"section\",\n  \"settings\": { },\n  \"elements\": [\n    {\n      \"id\": \"string\",\n      \"elType\": \"column\",\n      \"settings\": {\"_column_size\": 100},\n      \"elements\": [ ]\n    }\n  ]\n}\n"
        )
        content_guidance = (
            "Widgets to use: heading, text-editor, image, button, list, icon-list, spacer.\n"
            "Keep JSON concise and valid. Fill text fields with on-brief content. If a CTA exists, add a button.\n"
        )
        summarized = self._summarize_business_info(business_info)
        business_block = ("Business info:\n" + json.dumps(summarized, ensure_ascii=False)) if summarized else ""
        prompt = f"""
Generate Elementor section_data JSON for this section spec:
{json.dumps(section_spec, ensure_ascii=False)}

Style description:
{style_description}

{business_block}
{preserve}
{schema_hint}
{content_guidance}
"""
        agent_log('SectionGen', f"Generating section '{section_spec.get('type','section')}'")
        resp = model.generate_content(prompt)
        text = self._ai_get_text(resp)
        agent_log('SectionGen', f"Response length for '{section_spec.get('type','section')}': {len(text)}")
        try:
            _s_preview = (text or '')[:200].replace('\n', ' ')
        except Exception:
            _s_preview = ''
        agent_log('SectionGen', f"Response preview: {_s_preview}...")
        data = self._ai_parse_json(text)
        # Basic validation
        if not isinstance(data, dict) or data.get('elType') != 'section' or 'elements' not in data:
            raise ValueError("Generated section_data is invalid")
        return data

    def generate_ai_one_page_site(self, job_id: str, style_description: str, replace_images: bool = False, google_data: Optional[dict] = None):
        """AI-native flow: plan sections with Gemini, generate Elementor JSON, optionally store, assemble WXR, output XML"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        os.makedirs(work_dir, exist_ok=True)
        try:
            self.jobs[job_id]["status"] = "processing"
            agent_log('AI-OnePage', f'Start job {job_id}')

            # Prepare business info from google_data if provided
            business_info = None
            if google_data:
                try:
                    business_info = process_gbp_object(google_data)
                    self.jobs[job_id]["business_info"] = business_info
                    agent_log('AI-OnePage', f"Processed google_data for business: {business_info.get('business_name','N/A')}")
                except Exception as e:
                    agent_log('AI-OnePage', f"Failed to process google_data: {e}")

            # 1) Plan sections
            sections_plan = self._ai_generate_plan(style_description, business_info)
            agent_log('AI-OnePage', f"Planned {len(sections_plan)} sections: {[s.get('type') for s in sections_plan]}")

            # 2) Generate section_data for each plan entry
            elementor_sections: List[dict] = []
            for spec in sections_plan:
                try:
                    section_json = self._ai_generate_section_data(spec, style_description, business_info)
                    # Optional image enhancement
                    if replace_images and get_image_suggestion:
                        image_url = get_image_suggestion(style_description=style_description, element_context=spec.get('type', 'section'), element_type='image_widget')
                        if image_url and isinstance(section_json, dict):
                            try:
                                col = None
                                for el in section_json.get('elements', []):
                                    if el.get('elType') == 'column':
                                        col = el
                                        break
                                if col is not None:
                                    widgets = col.setdefault('elements', [])
                                    widgets.append({
                                        'id': str(uuid.uuid4())[:8],
                                        'elType': 'widget',
                                        'widgetType': 'image',
                                        'settings': { 'image': { 'url': image_url, 'id': '' } },
                                        'elements': []
                                    })
                            except Exception:
                                pass
                    elementor_sections.append(section_json)
                except Exception as e:
                    agent_log('AI-OnePage', f"Failed to generate section for spec {spec.get('type')}: {e}")
                    continue

            if not elementor_sections:
                raise ValueError("No sections were generated by the AI")
            agent_log('AI-OnePage', f'Generated {len(elementor_sections)} sections')

            # 3) Optionally store each section in DB (best-effort)
            try:
                supabase_url = os.getenv('SUPABASE_URL')
                supabase_key = os.getenv('SUPABASE_KEY')
                if supabase_url and supabase_key:
                    supabase = create_client(supabase_url, supabase_key)
                    for sec in elementor_sections:
                        section_record = {
                            'id': str(uuid.uuid4()),
                            'theme_id': None,
                            'category': 'ai_generated',
                            'content': json.dumps({ 'section_data': sec }, ensure_ascii=False)
                        }
                        try:
                            supabase.table('sections').insert(section_record).execute()
                        except Exception as e:
                            agent_log('AI-OnePage', f"Warning: failed to store generated section: {e}")
            except Exception as e:
                agent_log('AI-OnePage', f"Warning: Supabase storage unavailable: {e}")

            # 4) Assemble WXR using OnePageSiteGenerator base
            generator = self.onepage_generator
            agent_log('AI-OnePage', 'Assembling WordPress XML (WXR)')
            rss = generator.create_base_template()
            channel = rss.find('channel')
            item = ET.SubElement(channel, 'item')
            title = ET.SubElement(item, 'title'); title.text = 'Home'
            link = ET.SubElement(item, 'link'); link.text = 'https://example.com/'
            pubDate = ET.SubElement(item, 'pubDate'); pubDate.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
            creator = ET.SubElement(item, '{http://purl.org/dc/elements/1.1/}creator'); creator.text = 'admin'
            guid = ET.SubElement(item, 'guid'); guid.set('isPermaLink', 'false'); guid.text = f'https://example.com/?page_id=1'
            description = ET.SubElement(item, 'description'); description.text = ''
            content = ET.SubElement(item, '{http://purl.org/rss/1.0/modules/content/}encoded'); content.text = ''
            excerpt = ET.SubElement(item, '{http://wordpress.org/export/1.2/excerpt/}encoded'); excerpt.text = ''
            post_id = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_id'); post_id.text = '1'
            post_date = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date'); post_date.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            post_date_gmt = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_date_gmt'); post_date_gmt.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            comment_status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}comment_status'); comment_status.text = 'closed'
            ping_status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}ping_status'); ping_status.text = 'closed'
            post_name = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_name'); post_name.text = 'home'
            status = ET.SubElement(item, '{http://wordpress.org/export/1.2/}status'); status.text = 'publish'
            post_parent = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_parent'); post_parent.text = '0'
            menu_order = ET.SubElement(item, '{http://wordpress.org/export/1.2/}menu_order'); menu_order.text = '0'
            post_type = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_type'); post_type.text = 'page'
            post_password = ET.SubElement(item, '{http://wordpress.org/export/1.2/}post_password'); post_password.text = ''
            is_sticky = ET.SubElement(item, '{http://wordpress.org/export/1.2/}is_sticky'); is_sticky.text = '0'
            # Elementor meta
            meta_elementor = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
            meta_key = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_key'); meta_key.text = '_elementor_data'
            meta_value = ET.SubElement(meta_elementor, '{http://wordpress.org/export/1.2/}meta_value')
            meta_value.text = json.dumps(elementor_sections, ensure_ascii=False, separators=(',', ':'))
            # Elementor edit mode
            meta_edit_mode = ET.SubElement(item, '{http://wordpress.org/export/1.2/}postmeta')
            meta_key = ET.SubElement(meta_edit_mode, '{http://wordpress.org/export/1.2/}meta_key'); meta_key.text = '_elementor_edit_mode'
            meta_value = ET.SubElement(meta_edit_mode, '{http://wordpress.org/export/1.2/}meta_value'); meta_value.text = 'builder'

            output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
            # Write file
            tree = ET.ElementTree(rss)
            with open(output_path, 'wb') as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(f, encoding='UTF-8', xml_declaration=False)
            # Validate
            ET.parse(output_path)
            agent_log('AI-OnePage', f'Wrote XML to {output_path}')

            self.jobs[job_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "output_url": f"/download/{job_id}",
                "output_path": output_path,
                "type": "ai_onepage",
                "business_info": business_info or {}
            })
            agent_log('AI-OnePage', f'Job {job_id} completed')
        except Exception as e:
            agent_log('AI-OnePage', f"Error: {e}")
            traceback.print_exc()
            self.jobs[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e)
            })
        finally:
            try:
                shutil.rmtree(work_dir)
            except Exception:
                pass

    def validate_xml(self, file_path: str) -> bool:
        """Validate XML file structure"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            return True
        except ET.ParseError as e:
            print(f"XML Parse Error: {str(e)}")
            return False
        except Exception as e:
            print(f"Error validating XML: {str(e)}")
            return False

    def filter_unique_pages(self, xml_content: str) -> str:
        """Filter XML content to keep only one instance of each page type"""
        try:
            # Parse the XML content
            root = ET.fromstring(xml_content)
            
            # Dictionary to store unique pages by normalized title
            unique_pages = {}
            excluded_pages = []
            
            # Find all items (pages)
            items = root.findall(".//item")
            print("\nStarting page filtering process...")
            print("Found", len(items), "total pages in theme")
            
            # First pass: categorize pages
            for item in items:
                post_type = item.find(".//wp:post_type", namespaces={
                    'wp': 'http://wordpress.org/export/1.2/'
                })
                
                # Skip if not a page
                if post_type is None or post_type.text != 'page':
                    continue
                    
                title = item.find("title")
                if title is not None and title.text:
                    title_text = title.text.strip()
                    base_title = self._get_base_title(title_text)  # Get base title without numbers
                    
                    content = item.find(".//content:encoded", namespaces={
                        'content': 'http://purl.org/rss/1.0/modules/content/'
                    })
                    content_length = len(content.text) if content is not None and content.text else 0
                    
                    print(f"\nAnalyzing page: {title_text}")
                    print(f"Base title: {base_title}")
                    print(f"Content length: {content_length} characters")
                    
                    if base_title not in unique_pages:
                        print(f"✓ Selected '{title_text}' as first instance of '{base_title}' type")
                        unique_pages[base_title] = {
                            'item': item,
                            'title': title_text,
                            'content_length': content_length
                        }
                    else:
                        # Compare content length with existing page
                        existing_page = unique_pages[base_title]
                        if content_length > existing_page['content_length']:
                            print(f"↻ Replacing '{existing_page['title']}' with '{title_text}' (more content)")
                            excluded_pages.append(existing_page['title'])
                            unique_pages[base_title] = {
                                'item': item,
                                'title': title_text,
                                'content_length': content_length
                            }
                        else:
                            print(f"✗ Excluding '{title_text}' (keeping existing '{existing_page['title']}')")
                            excluded_pages.append(title_text)
            
            # Create new XML with filtered pages
            new_root = ET.Element(root.tag, root.attrib)
            channel = ET.SubElement(new_root, "channel")
            
            # Copy channel metadata
            for child in root.find("channel"):
                if child.tag != "item":
                    channel.append(ET.fromstring(ET.tostring(child)))
            
            # Add filtered pages
            for page_data in unique_pages.values():
                channel.append(ET.fromstring(ET.tostring(page_data['item'])))
            
            # Print summary
            print("\nPage Filtering Summary:")
            print("----------------------")
            print(f"Total pages found: {len(items)}")
            print(f"Unique page types: {len(unique_pages)}")
            print(f"Pages excluded: {len(excluded_pages)}")
            print("\nSelected Pages:")
            for base_title, page_data in unique_pages.items():
                print(f"- {page_data['title']} (type: {base_title})")
            print("\nExcluded Pages:")
            for title in excluded_pages:
                print(f"- {title}")
            
            # Convert back to string
            return ET.tostring(new_root, encoding='unicode', method='xml')
            
        except Exception as e:
            print(f"Error filtering unique pages: {e}")
            return xml_content

    def _get_base_title(self, title: str) -> str:
        """Extract base title by removing numbers and common suffixes"""
        # Remove numbers and special characters from end of title
        base = re.sub(r'\s*[-–_]\s*\d+$', '', title)
        base = re.sub(r'\s+\d+$', '', base)
        
        # Remove common suffixes
        base = re.sub(r'\s*[-–_]\s*(copy|duplicate|version|v\d+)$', '', base, flags=re.IGNORECASE)
        
        # Normalize spacing
        base = ' '.join(base.split())
        
        # Make case insensitive
        return base.lower()

    
    def process_theme(self, job_id: str, input_path: str, style_description: str, skip_theme_creation: bool = False, replace_images: bool = False, gbp_object: dict = None):
        """Process theme transformation"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        theme_id = None
        transformed_path = None
        output_path = None
        
        try:
            # Update job status
            self.jobs[job_id]["status"] = "processing"
            
            # Create job working directory
            os.makedirs(work_dir, exist_ok=True)
            
            # Process GBP object if provided
            business_info = {}
            preservation_prompt = ""
            if gbp_object:
                business_info = process_gbp_object(gbp_object)
                preservation_prompt = create_gbp_preservation_prompt(business_info)
                print(f"Processing with GBP object for business: {business_info.get('business_name', 'Unknown')}")
                # Store business info in job for later use
                self.jobs[job_id]["business_info"] = business_info
                self.jobs[job_id]["gbp_object"] = gbp_object
            
            # Validate input XML
            if not self.validate_xml(input_path):
                raise ValueError(f"Invalid input XML file: {input_path}")
            
            # Step 1: Extract content
            print(f"Extracting content from {input_path}...")
            try:
                if skip_theme_creation:
                    pages_data, sections_data = self.extraction_agent.extract_content_only(input_path)
                else:
                    theme_id, pages_data, sections_data = self.extraction_agent.process_theme(input_path)
            except ET.ParseError as e:
                raise ValueError(f"XML parsing error during extraction: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error during extraction: {str(e)}")
            
            # Step 2: Transform content with GBP preservation if provided
            print(f"Transforming content with style: {style_description}...")
            
            # Combine style description with preservation prompt if GBP object is provided
            final_style_description = style_description
            if preservation_prompt:
                final_style_description = f"{style_description}\n\n{preservation_prompt}"
                print("Applied GBP preservation instructions to transformation")
            
            transformation_result = self.transformation_agent.transform_theme_content(
                theme_id or job_id,
                final_style_description,
                filtered_pages=pages_data if skip_theme_creation else None,
                filtered_sections=sections_data if skip_theme_creation else None
            )
            
            # Ensure proper structure for text transformations and color palette
            if 'text_transformations' not in transformation_result:
                transformation_result['text_transformations'] = []
                
            if 'color_palette' not in transformation_result:
                transformation_result['color_palette'] = {'original_colors': [], 'new_colors': []}
            elif isinstance(transformation_result['color_palette'], dict):
                if 'color_palette' in transformation_result['color_palette']:
                    # Handle nested color_palette structure
                    transformation_result['color_palette'] = transformation_result['color_palette']['color_palette']
            
            # Add business info to transformation result if GBP object was provided
            if business_info:
                transformation_result['business_info'] = business_info
                transformation_result['gbp_preserved'] = True
            
            # Generate transformation output path
            transformed_path = os.path.join(work_dir, f"transformed_{job_id}.json")
            with open(transformed_path, 'w', encoding='utf-8') as f:
                json.dump(transformation_result, f, ensure_ascii=False, indent=2)
            
            # Save debug information
            debug_path = os.path.join(work_dir, f"debug_transformed_{job_id}.json")
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'input': {
                        'theme_id': theme_id,
                        'style_description': style_description,
                        'final_style_description': final_style_description,
                        'gbp_object_provided': bool(gbp_object),
                        'business_info': business_info,
                        'filtered_pages_count': len(pages_data) if pages_data else 0,
                        'filtered_sections_count': len(sections_data) if sections_data else 0
                    },
                    'transformation_result': transformation_result,
                    'text_count': len(transformation_result.get('text_transformations', [])),
                    'color_count': len(transformation_result.get('color_palette', {}).get('new_colors', []))
                }, f, ensure_ascii=False, indent=2)
            
            # Step 3: Apply transformations
            print(f"Applying transformations to generate new theme...")
            output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
            
            # Apply the transformations using the standalone function
            # Include replace_images parameter and style_description in the transformation data
            # First, update the transformation data to include replace_images flag
            if replace_images:
                # Read the transformation data
                with open(transformed_path, 'r', encoding='utf-8') as f:
                    transform_data = json.load(f)
                
                # Add replace_images flag and ensure style_description is included
                transform_data['replace_images'] = replace_images
                if 'style_description' not in transform_data:
                    transform_data['style_description'] = style_description
                
                # Write the updated transformation data back
                with open(transformed_path, 'w', encoding='utf-8') as f:
                    json.dump(transform_data, f, indent=2)
                
                print(f"Added replace_images=True to transformation data for job {job_id}")
            
            # Call appropriate replacement function based on replace_images flag
            if replace_images:
                replace_with_images(
                    input_path,
                    transformed_path,
                    output_path
                )
            else:
                replace_text_and_colors(
                    input_path,
                    transformed_path,
                    output_path
                )
            
            # Update job status
            self.jobs[job_id].update({
                "status": "completed", 
                "completed_at": datetime.utcnow().isoformat(),
                "output_path": output_path,
                "output_url": f"/download/{job_id}"
            })
            
            # Only store transformation data if we created a new theme
            if not skip_theme_creation and theme_id:
                try:
                    # Store transformation data
                    transformation_id = str(uuid.uuid4())
                    transformation_data = {
                        'id': transformation_id,
                        'theme_id': theme_id,
                        'texts': transformation_result.get('text_transformations', []),
                        'colors': transformation_result.get('color_palette', {}).get('new_colors', []),
                        'created_at': datetime.utcnow().isoformat(),
                        'gbp_preserved': bool(business_info)
                    }
                    
                    # Write debug info
                    debug_dir = os.path.join(os.path.dirname(output_path), "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(os.path.join(debug_dir, "transformation_debug.json"), 'w', encoding='utf-8') as f:
                        json.dump({
                            'raw_transformation': transformation_result,
                            'stored_transformation': transformation_data
                        }, f, indent=2, ensure_ascii=False)
                    
                    # Insert into database
                    supabase_url = os.getenv('SUPABASE_URL')
                    supabase_key = os.getenv('SUPABASE_KEY')
                    
                    if supabase_url and supabase_key:
                        supabase = create_client(supabase_url, supabase_key)
                        supabase.table('transformation_data').insert(transformation_data).execute()
                        print(f"Stored transformation data with ID: {transformation_id}")
                except Exception as e:
                    print(f"Failed to store transformation data: {e}")
                
        except Exception as e:
            print(f"Error processing theme: {e}")
            traceback.print_exc()
            
            self.jobs[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e)
            })
            
        finally:
            # Cleanup work directory
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")

    def generate_one_page_site(self, job_id: str, query: str, style_description: str = None, replace_images: bool = False, gbp_object: dict = None):
        """Generate a one-page site from user query"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        try:
            self.jobs[job_id]["status"] = "processing"
            os.makedirs(work_dir, exist_ok=True)
            print(f"Generating one-page site from query: {query}...")
            
            # Process GBP object if provided
            business_info = {}
            preservation_prompt = ""
            if gbp_object:
                business_info = process_gbp_object(gbp_object)
                preservation_prompt = create_gbp_preservation_prompt(business_info)
                print(f"Processing with GBP object for business: {business_info.get('business_name', 'Unknown')}")
                self.jobs[job_id]["business_info"] = business_info
                self.jobs[job_id]["gbp_object"] = gbp_object
            
            temp_output_path = os.path.join(work_dir, "onepage_temp.xml")
            combined_query = query
            if style_description and style_description.strip():
                combined_query = f"{query} with {style_description}"
            try:
                self.onepage_generator.create_one_page_site(combined_query, temp_output_path)
            except Exception as e:
                raise ValueError(f"Error generating one-page site: {str(e)}")
            if not self.validate_xml(temp_output_path):
                raise ValueError("Generated one-page site XML is invalid")
            print(f"Extracting content from generated site...")
            try:
                theme_id, pages_data, sections_data = self.extraction_agent.process_theme(temp_output_path)
            except ET.ParseError as e:
                raise ValueError(f"XML parsing error: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error during extraction: {str(e)}")
            print(f"Applying style: {combined_query}...")
            
            # Combine style description with preservation prompt if GBP object is provided
            final_style_description = combined_query
            if preservation_prompt:
                final_style_description = f"{combined_query}\n\n{preservation_prompt}"
                print("Applied GBP preservation instructions to transformation")
            
            transformation_result = self.transformation_agent.transform_theme_content(theme_id, final_style_description)
            if 'text_transformations' not in transformation_result:
                transformation_result['text_transformations'] = []
            if 'color_palette' not in transformation_result:
                transformation_result['color_palette'] = {'original_colors': [], 'new_colors': []}
            elif isinstance(transformation_result['color_palette'], dict):
                if 'color_palette' in transformation_result['color_palette']:
                    transformation_result['color_palette'] = transformation_result['color_palette']['color_palette']
            
            # Add business info to transformation result if GBP object was provided
            if business_info:
                transformation_result['business_info'] = business_info
                transformation_result['gbp_preserved'] = True
            
            transformed_path = os.path.join(work_dir, f"transformed_{theme_id}.json")
            with open(transformed_path, 'w', encoding='utf-8') as f:
                json.dump(transformation_result, f, ensure_ascii=False, indent=2)
            debug_path = os.path.join(work_dir, f"debug_transformed_{job_id}.json")
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'input': {
                        'theme_id': theme_id,
                        'style_description': style_description,
                        'query': query,
                        'combined_query': combined_query,
                        'final_style_description': final_style_description,
                        'gbp_object_provided': bool(gbp_object),
                        'business_info': business_info
                    },
                    'transformation_result': transformation_result,
                    'text_count': len(transformation_result.get('text_transformations', [])),
                    'color_count': len(transformation_result.get('color_palette', {}).get('new_colors', []))
                }, f, ensure_ascii=False, indent=2)
            output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
            if replace_images:
                # Add replace_images flag to transformation data
                with open(transformed_path, 'r', encoding='utf-8') as f:
                    transform_data = json.load(f)
                transform_data['replace_images'] = True
                if 'style_description' not in transform_data:
                    transform_data['style_description'] = style_description
                with open(transformed_path, 'w', encoding='utf-8') as f:
                    json.dump(transform_data, f, indent=2)
                replace_with_images(temp_output_path, transformed_path, output_path)
            else:
                replace_text_and_colors(temp_output_path, transformed_path, output_path)
            if not self.validate_xml(output_path):
                raise Exception("Output XML validation failed - the generated file is not a valid XML document")
            self.jobs[job_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "output_url": f"/download/{job_id}",
                "job_type": "one_page_site"
            })
            print(f"One-page site generation completed successfully! Output: {output_path}")
        except Exception as e:
            print(f"Error generating one-page site: {e}")
            self.jobs[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e)
            })
            raise
        finally:
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")

    def generate_multi_page_site(self, job_id: str, query: str, style_description: str = None, replace_images: bool = False, gbp_object: dict = None):
        """Generate a multi-page site from user query"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        try:
            self.jobs[job_id]["status"] = "processing"
            os.makedirs(work_dir, exist_ok=True)
            print(f"Generating multi-page site from query: {query}...")
            
            # Process GBP object if provided
            business_info = {}
            preservation_prompt = ""
            if gbp_object:
                business_info = process_gbp_object(gbp_object)
                preservation_prompt = create_gbp_preservation_prompt(business_info)
                print(f"Processing with GBP object for business: {business_info.get('business_name', 'Unknown')}")
                self.jobs[job_id]["business_info"] = business_info
                self.jobs[job_id]["gbp_object"] = gbp_object
            
            temp_output_path = os.path.join(work_dir, "multipage_temp.xml")
            # IMPORTANT: Only use the user's query to select pages. Do NOT mix in style or GBP data.
            combined_query = query  # kept for backward-compatible debug fields below
            try:
                # Pass only the original query for page selection; provide style separately for styling/colors
                self.multipage_generator.create_multi_page_site(query, temp_output_path, style_description)
            except Exception as e:
                raise ValueError(f"Error generating multi-page site: {str(e)}")
            if not self.validate_xml(temp_output_path):
                raise ValueError("Generated multi-page site XML is invalid")
            print(f"Extracting content from generated site...")
            try:
                theme_id, pages_data, sections_data = self.extraction_agent.process_theme(temp_output_path)
            except ET.ParseError as e:
                debug_path = os.path.join(self.base_dir, "output", f"debug_{job_id}.xml")
                shutil.copy(temp_output_path, debug_path)
                raise ValueError(f"XML parsing error in {debug_path}: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error during extraction: {str(e)}")
            print(f"Applying style: {style_description}...")
            
            # Combine style description with preservation prompt if GBP object is provided
            final_style_description = style_description or ""
            if preservation_prompt:
                final_style_description = f"{final_style_description}\n\n{preservation_prompt}".strip()
                print("Applied GBP preservation instructions to transformation")
            
            transformation_result = self.transformation_agent.transform_theme_content(theme_id, final_style_description)
            if 'text_transformations' not in transformation_result:
                transformation_result['text_transformations'] = []
            if 'color_palette' not in transformation_result:
                transformation_result['color_palette'] = {'original_colors': [], 'new_colors': []}
            elif isinstance(transformation_result['color_palette'], dict):
                if 'color_palette' in transformation_result['color_palette']:
                    transformation_result['color_palette'] = transformation_result['color_palette']['color_palette']
            
            # Add business info to transformation result if GBP object was provided
            if business_info:
                transformation_result['business_info'] = business_info
                transformation_result['gbp_preserved'] = True
            
            transformed_path = os.path.join(work_dir, f"transformed_{theme_id}.json")
            with open(transformed_path, 'w', encoding='utf-8') as f:
                json.dump(transformation_result, f, ensure_ascii=False, indent=2)
            debug_path = os.path.join(work_dir, f"debug_transformed_{job_id}.json")
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'input': {
                        'theme_id': theme_id,
                        'style_description': style_description,
                        'query': query,
                        'combined_query': combined_query,
                        'final_style_description': final_style_description,
                        'gbp_object_provided': bool(gbp_object),
                        'business_info': business_info
                    },
                    'transformation_result': transformation_result,
                    'text_count': len(transformation_result.get('text_transformations', [])),
                    'color_count': len(transformation_result.get('color_palette', {}).get('new_colors', []))
                }, f, ensure_ascii=False, indent=2)
            output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
            if replace_images:
                with open(transformed_path, 'r', encoding='utf-8') as f:
                    transform_data = json.load(f)
                transform_data['replace_images'] = True
                if 'style_description' not in transform_data:
                    transform_data['style_description'] = style_description
                with open(transformed_path, 'w', encoding='utf-8') as f:
                    json.dump(transform_data, f, indent=2)
                replace_with_images(temp_output_path, transformed_path, output_path)
            else:
                replace_text_and_colors(temp_output_path, transformed_path, output_path)
            if not self.validate_xml(output_path):
                raise Exception("Output XML validation failed - the generated file is not a valid XML document")
            self.jobs[job_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "output_url": f"/download/{job_id}",
                "job_type": "multi_page_site"
            })
            # Save the palette and mapping in the transformation_result for later use
            if hasattr(self.multipage_generator, 'generated_palette') and hasattr(self.multipage_generator, 'generated_mapping'):
                transformation_result['full_palette'] = self.multipage_generator.generated_palette
                transformation_result['elementor_mapping'] = self.multipage_generator.generated_mapping
                transformation_result['style_description'] = self.multipage_generator.generated_style_description
            print(f"Multi-page site generation completed successfully! Output: {output_path}")
        except Exception as e:
            print(f"Error generating multi-page site: {e}")
            self.jobs[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e)
            })
            raise
        finally:
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")

    def process_theme_by_id(self, job_id: str, theme_id: str, style_description: str, replace_images: bool = False, gbp_object: dict = None):
        """Process a theme transformation by its ID"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
        try:
            try:
                valid_theme_id = str(uuid.UUID(theme_id))
            except ValueError:
                raise ValueError(f"Provided theme_id '{theme_id}' is not a valid UUID.")
            self.jobs[job_id]["status"] = "processing"
            os.makedirs(work_dir, exist_ok=True)
            
            # Process GBP object if provided
            business_info = {}
            preservation_prompt = ""
            if gbp_object:
                business_info = process_gbp_object(gbp_object)
                preservation_prompt = create_gbp_preservation_prompt(business_info)
                print(f"Processing with GBP object for business: {business_info.get('business_name', 'Unknown')}")
                self.jobs[job_id]["business_info"] = business_info
                self.jobs[job_id]["gbp_object"] = gbp_object
            
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            if not supabase_url or not supabase_key:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            supabase = create_client(supabase_url, supabase_key)
            transformation_data = None
            if not style_description:
                try:
                    trans_result = supabase.table('transformation_data').select('*').eq('theme_id', valid_theme_id).execute()
                    if trans_result.data:
                        transformation_data = trans_result.data[0]
                        print(f"Found existing transformation data for theme {valid_theme_id}")
                except Exception as e:
                    print(f"Error fetching transformation data: {e}")
            theme_result = supabase.table('themes').select('*').eq('id', valid_theme_id).execute()
            if not theme_result.data:
                raise ValueError(f"Theme with ID '{valid_theme_id}' not found in database")
            theme_data = theme_result.data[0]
            xml_content = None
            for field in ['content', 'xml_content', 'xml_data', 'file_content', 'theme_content', 'data']:
                if field in theme_data and theme_data.get(field):
                    xml_content = theme_data.get(field)
                    break
            if not xml_content:
                raise ValueError(f"No XML content found for theme ID '{valid_theme_id}'")
            input_path = os.path.join(work_dir, f"input_{valid_theme_id}.xml")
            with open(input_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            print(f"Saved theme XML to {input_path}")
            self.jobs[job_id].update({
                "theme_id": valid_theme_id,
                "theme_title": theme_data.get('title', 'Unknown theme'),
                "input_path": input_path,
                "output_path": output_path
            })
            if not self.validate_xml(input_path):
                raise ValueError(f"Invalid XML content for theme ID: {valid_theme_id}")
            print(f"Extracting content from theme ID: {valid_theme_id}...")
            try:
                # Extract posts for transformation
                extracted_posts = self.extraction_agent.extract_posts_for_transformation(input_path, valid_theme_id)
                # Extract pages and sections as before
                extracted_theme_id, pages_data, sections_data = self.extraction_agent.process_theme(input_path)
                print(f"Transforming content with style: {style_description or 'default style'}...")
                
                # Combine style description with preservation prompt if GBP object is provided
                final_style_description = style_description or ""
                if preservation_prompt:
                    final_style_description = f"{final_style_description}\n\n{preservation_prompt}"
                    print("Applied GBP preservation instructions to transformation")
                
                # Pass extracted_posts to transformation agent
                transformation_result = self.transformation_agent.transform_theme_content(
                    extracted_theme_id,
                    final_style_description,
                    extracted_posts=extracted_posts
                )
                
                # Add business info to transformation result if GBP object was provided
                if business_info:
                    transformation_result['business_info'] = business_info
                    transformation_result['gbp_preserved'] = True
                
                transformation_path = os.path.join(work_dir, f"transformation_{valid_theme_id}.json")
                with open(transformation_path, 'w', encoding='utf-8') as f:
                    json.dump(transformation_result, f, indent=2)
                print(f"Applying transformations to generate new theme...")
                if replace_images:
                    with open(transformation_path, 'r', encoding='utf-8') as f:
                        transform_data = json.load(f)
                    transform_data['replace_images'] = True
                    if 'style_description' not in transform_data:
                        transform_data['style_description'] = style_description
                    with open(transformation_path, 'w', encoding='utf-8') as f:
                        json.dump(transform_data, f, indent=2)
                    replace_with_images(input_path, transformation_path, output_path)
                else:
                    replace_text_and_colors(input_path, transformation_path, output_path)
            except Exception as e:
                raise ValueError(f"Error during theme processing: {str(e)}")
            self.jobs[job_id].update({
                "status": "completed", 
                "completed_at": datetime.utcnow().isoformat(),
                "output_url": f"/download/{job_id}"
            })
            try:
                transformation_id = str(uuid.uuid4())
                text_transformations = transformation_result.get('text_transformations', [])
                color_palette = transformation_result.get('color_palette', {})
                transformation_data = {
                    'id': transformation_id,
                    'theme_id': valid_theme_id,
                    'texts': text_transformations,
                    'colors': color_palette.get('new_colors', []),
                    'created_at': datetime.utcnow().isoformat(),
                    'gbp_preserved': bool(business_info)
                }
                debug_dir = os.path.join(os.path.dirname(output_path), "debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, "transformation_debug.json"), 'w', encoding='utf-8') as f:
                    json.dump({
                        'raw_transformation': transformation_result,
                        'stored_transformation': transformation_data
                    }, f, indent=2, ensure_ascii=False)
                supabase.table('transformation_data').insert(transformation_data).execute()
                print(f"Stored transformation data with ID: {transformation_id}")
                print(f"Saved {len(text_transformations)} transformed texts and {len(color_palette.get('new_colors', []))} colors")
            except Exception as e:
                print(f"Failed to store transformation data: {e}")
            if not self.validate_xml(output_path):
                raise ValueError("Output XML validation failed - the generated file is not valid XML")
            print(f"Theme transformation completed successfully! Output: {output_path}")
        except Exception as e:
            print(f"Error processing theme: {e}")
            traceback.print_exc()
            self.jobs[job_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e)
            })
        finally:
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")

# Define request models
class ThemeTransformRequest(BaseModel):
    style_description: str
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class ThemeTransformByIdRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class ThemeGenerateRequest(BaseModel):
    style_description: str
    page_count: Optional[int] = 1
    google_data: Optional[dict] = None

class ThemeStoreRequest(BaseModel):
    theme_name: str
    style_description: Optional[str] = None
    google_data: Optional[dict] = None

class SectionEvaluationRequest(BaseModel):
    theme_id: str
    detailed_analysis: Optional[bool] = True
    google_data: Optional[dict] = None

# Define request models for site generation
class OnePageSiteRequest(BaseModel):
    query: str = Field(..., description="The description of sections to include in the site, e.g., 'hero, about, services, contact'")
    style_description: Optional[str] = "modern professional style with clean design"
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

class MultiPageSiteRequest(BaseModel):
    query: str = Field(..., description="The description of pages to include in the site, e.g., 'home, about, services, contact'")
    style_description: Optional[str] = "modern professional style with clean design"
    replace_images: Optional[bool] = False
    google_data: Optional[dict] = None

# Initialize orchestrator
orchestrator = ThemeTransformerOrchestrator()

# --- Google Places OnePage Site Generation ---
# Note: Now using existing working generators instead of custom implementation

def process_gbp_object(gbp_data: dict) -> dict:
    """
    Process Google Business Profile object and extract business information
    that should be preserved during transformation.
    """
    if not gbp_data or not isinstance(gbp_data, dict):
        return {}
    
    # Handle both direct result format and full Google Places API response
    if "result" in gbp_data:
        result = gbp_data["result"]
    else:
        result = gbp_data
    
    # Process photos to get actual URLs if photo_reference is provided
    processed_photos = []
    if result.get("photos"):
        for photo in result["photos"]:
            if isinstance(photo, dict):
                photo_info = {
                    "photo_reference": photo.get("photo_reference", ""),
                    "height": photo.get("height", 0),
                    "width": photo.get("width", 0),
                    "html_attributions": photo.get("html_attributions", [])
                }
                # You can add logic here to construct actual photo URLs if needed
                # For now, we'll store the photo_reference which can be used to fetch the actual image
                processed_photos.append(photo_info)
    
    # Process reviews to extract meaningful information
    processed_reviews = []
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
                processed_reviews.append(review_info)
    
    # Process opening hours to get both formats
    processed_opening_hours = {}
    if result.get("opening_hours"):
        processed_opening_hours = {
            "open_now": result["opening_hours"].get("open_now", False),
            "weekday_text": result["opening_hours"].get("weekday_text", []),
            "periods": result["opening_hours"].get("periods", [])
        }
    
    # Also check current_opening_hours if available
    if result.get("current_opening_hours"):
        processed_opening_hours.update({
            "current_open_now": result["current_opening_hours"].get("open_now", False),
            "current_weekday_text": result["current_opening_hours"].get("weekday_text", []),
            "current_periods": result["current_opening_hours"].get("periods", [])
        })
    
    # Extract business information that should be preserved
    business_info = {
        "business_name": result.get("name", ""),
        "address": result.get("formatted_address", ""),
        "phone": result.get("formatted_phone_number", ""),
        "international_phone": result.get("international_phone_number", ""),
        "website": result.get("website", ""),
        "business_status": result.get("business_status", ""),
        "rating": result.get("rating", 0),
        "total_reviews": result.get("user_ratings_total", 0),
        "opening_hours": processed_opening_hours,
        "photos": processed_photos,
        "reviews": processed_reviews,
        "geometry": result.get("geometry", {}),
        "types": result.get("types", []),
        "vicinity": result.get("vicinity", ""),
        "place_id": result.get("place_id", ""),
        "url": result.get("url", ""),
        "utc_offset": result.get("utc_offset", 0),
        "icon": result.get("icon", ""),
        "icon_background_color": result.get("icon_background_color", ""),
        "plus_code": result.get("plus_code", {}),
        "adr_address": result.get("adr_address", ""),
        "address_components": result.get("address_components", []),
        "html_attributions": gbp_data.get("html_attributions", []),
        "reference": result.get("reference", ""),
        "status": gbp_data.get("status", "")
    }
    
    return business_info

def create_gbp_preservation_prompt(business_info: dict) -> str:
    """
    Create a prompt that instructs GPT to preserve business information
    while transforming other content.
    """
    if not business_info:
        return ""
    
    preservation_instructions = """
IMPORTANT: The following business information must be preserved exactly as provided and NOT transformed:
"""
    
    if business_info.get("business_name"):
        preservation_instructions += f"- Business Name: '{business_info['business_name']}' must remain unchanged\n"
    
    if business_info.get("address"):
        preservation_instructions += f"- Address: '{business_info['address']}' must remain unchanged\n"
    
    if business_info.get("phone"):
        preservation_instructions += f"- Phone: '{business_info['phone']}' must remain unchanged\n"
    
    if business_info.get("international_phone"):
        preservation_instructions += f"- International Phone: '{business_info['international_phone']}' must remain unchanged\n"
    
    if business_info.get("website"):
        preservation_instructions += f"- Website: '{business_info['website']}' must remain unchanged\n"
    
    # Handle opening hours (both regular and current)
    opening_hours = business_info.get("opening_hours", {})
    if opening_hours:
        weekday_text = opening_hours.get("weekday_text", [])
        current_weekday_text = opening_hours.get("current_weekday_text", [])
        
        if weekday_text:
            preservation_instructions += f"- Opening Hours: {weekday_text} must remain unchanged\n"
        elif current_weekday_text:
            preservation_instructions += f"- Opening Hours: {current_weekday_text} must remain unchanged\n"
    
    # Handle reviews
    reviews = business_info.get("reviews", [])
    if reviews:
        preservation_instructions += f"- Reviews: All review content from {len(reviews)} reviews must remain unchanged, including:\n"
        for i, review in enumerate(reviews[:3]):  # Show first 3 reviews as examples
            author = review.get("author_name", "Anonymous")
            text = review.get("text", "").strip()
            rating = review.get("rating", 0)
            if text:  # Only include reviews with text
                preservation_instructions += f"  * {author} ({rating} stars): '{text[:100]}...' must remain unchanged\n"
            else:
                preservation_instructions += f"  * {author} ({rating} stars): Rating only, no text content\n"
        if len(reviews) > 3:
            preservation_instructions += f"  * And {len(reviews) - 3} more reviews with their exact content\n"
    
    # Handle photos
    photos = business_info.get("photos", [])
    if photos:
        preservation_instructions += f"- Photos: All {len(photos)} photo references must remain unchanged:\n"
        for i, photo in enumerate(photos[:3]):  # Show first 3 photos as examples
            photo_ref = photo.get("photo_reference", "")
            if photo_ref:
                preservation_instructions += f"  * Photo {i+1}: Reference '{photo_ref[:20]}...' must remain unchanged\n"
        if len(photos) > 3:
            preservation_instructions += f"  * And {len(photos) - 3} more photo references\n"
    
    # Handle rating information
    rating = business_info.get("rating", 0)
    total_reviews = business_info.get("total_reviews", 0)
    if rating > 0:
        preservation_instructions += f"- Rating: {rating} stars from {total_reviews} reviews must remain unchanged\n"
    
    preservation_instructions += """
Transform all other content according to the style description, but ensure the above business information is preserved exactly as provided.
"""
    
    return preservation_instructions

@app.post("/generate/google-onepage")
async def generate_google_onepage(
    request: GoogleOnePageRequest,
    background_tasks: BackgroundTasks
):
    """Generate a one-page WordPress site from Google Places API data"""
    try:
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        # Extract parameters from google_data
        google_business_data = request.google_data
        style_description = google_business_data.get("style_description", "modern professional style with clean design")
        replace_images = google_business_data.get("replace_images", False)
        
        # Process GBP object (the actual business data should be in 'result' key or directly in google_data)
        business_info = process_gbp_object(google_business_data)
        preservation_prompt = create_gbp_preservation_prompt(business_info)
        
        # Create a business query from the Google data
        business_name = business_info.get("business_name", "Business")
        business_query = f"Create a website for {business_name} with hero section, about us, services, gallery, reviews, contact, and map"
        
        # Combine style description with preservation prompt
        final_style_description = style_description
        if preservation_prompt:
            final_style_description = f"{style_description}\n\n{preservation_prompt}"
            print("Applied GBP preservation instructions to Google OnePage generation")
        
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'type': 'google_onepage',
            'style_description': final_style_description,
            'replace_images': replace_images,
            'gbp_object': google_business_data,
            'business_info': business_info
        }
        
        # Use the existing working orchestrator method instead of custom implementation
        background_tasks.add_task(
            orchestrator.generate_one_page_site,
            job_id,
            business_query,
            final_style_description,
            replace_images,
            google_business_data  # Pass as gbp_object
        )
        
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Google one-page site generation started'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/ai-onepage")
async def generate_ai_onepage(
    request: AIOnePageRequest,
    background_tasks: BackgroundTasks
):
    """AI-native one-page site generation (Planner + Section Generator)"""
    try:
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'type': 'ai_onepage',
            'style_description': request.style_description,
            'replace_images': request.replace_images,
            'gbp_object': request.google_data
        }
        background_tasks.add_task(
            orchestrator.generate_ai_one_page_site,
            job_id,
            request.style_description,
            request.replace_images,
            request.google_data
        )
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='AI one-page generation started'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transform")
async def transform_theme(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    style_description: str = Form(...),
    replace_images: bool = Form(False),
    google_data: Optional[str] = Form(None)
):
    """Transform a WordPress theme file with the given style description"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        # Parse google_data if provided
        gbp_data = None
        if google_data:
            try:
                gbp_data = json.loads(google_data)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid google_data JSON format")
        
        # Create job record
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'source_file': file.filename,
            'style_description': style_description,
            'replace_images': replace_images,
            'gbp_object': gbp_data
        }
        
        # Save the uploaded file
        input_path = os.path.join(orchestrator.base_dir, "uploads", f"{job_id}_{file.filename}")
        with open(input_path, "wb") as f:
            f.write(file.file.read())
        
        # Start transformation in background
        background_tasks.add_task(
            orchestrator.process_theme,
            job_id,
            input_path,
            style_description,
            False,  # skip_theme_creation
            replace_images,  # Add replace_images parameter
            gbp_data  # Pass google_data
        )
        
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Theme transformation started'
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/onepage")
async def generate_onepage_theme(
    request: OnePageSiteRequest,
    background_tasks: BackgroundTasks
):
    """Generate a single-page WordPress theme"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        # Create job record
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'style_description': request.style_description,
            'query': request.query,
            'type': 'onepage',
            'replace_images': request.replace_images,
            'gbp_object': request.google_data
        }
        # Start generation in background
        background_tasks.add_task(
            orchestrator.generate_one_page_site,
            job_id,
            request.query,
            request.style_description,
            request.replace_images,
            request.google_data
        )
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Single-page theme generation started'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/multipage")
async def generate_multipage_theme(
    request: MultiPageSiteRequest,
    background_tasks: BackgroundTasks
):
    """Generate a multi-page WordPress theme"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        # Create job record
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'style_description': request.style_description,
            'query': request.query,
            'type': 'multipage',
            'replace_images': request.replace_images,
            'gbp_object': request.google_data
        }
        
        # Start generation in background
        background_tasks.add_task(
            orchestrator.generate_multi_page_site,
            job_id,
            request.query,
            request.style_description,
            request.replace_images,  # Pass replace_images
            request.google_data
        )
        
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Multi-page theme generation started'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a transformation job"""
    if job_id not in orchestrator.jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = orchestrator.jobs[job_id]
    response = {
        'job_id': job_id,
        'status': job['status'],
        'created_at': job['created_at'],
        'completed_at': job.get('completed_at'),
        'error': job.get('error'),
        'output_url': job.get('output_url'),
        'job_type': job.get('type', 'unknown'),
        'gbp_preserved': job.get('gbp_preserved', False),
        'business_info': job.get('business_info', {})
    }
    
    return response

@app.get("/download/{job_id}")
async def download_transformed_theme(job_id: str):
    """Download the transformed theme file"""
    if job_id not in orchestrator.jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = orchestrator.jobs[job_id]
    if job['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Theme transformation not completed")
    
    output_path = job.get('output_path')
    if not output_path:
        # If output_path is not explicitly set, construct the default path
        output_path = os.path.join(orchestrator.base_dir, "output", f"{job_id}.xml")
    
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail=f"Transformed theme file not found at {output_path}")
    
    return FileResponse(
        output_path,
        media_type='application/xml',
        filename=f"transformed_theme_{job_id}.xml"
    )

@app.post("/transform-by-id")
async def transform_theme_by_id(
    request: ThemeTransformByIdRequest,
    background_tasks: BackgroundTasks
):
    """Transform a theme by its ID from the database"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        # Create job record
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'source_theme_id': request.theme_id,
            'style_description': request.style_description,
            'replace_images': request.replace_images,
            'gbp_object': request.google_data
        }
        
        # Start transformation in background
        background_tasks.add_task(
            orchestrator.process_theme_by_id,
            job_id,
            request.theme_id,
            request.style_description,
            request.replace_images,  # Pass replace_images
            request.google_data
        )
        
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Theme transformation started'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/store-complete-theme")
async def store_complete_theme(
    file: UploadFile = File(...),
    theme_name: str = Form(...),
    style_description: Optional[str] = Form(None)
):
    """Store a complete WordPress theme with XML content and extract all elements"""
    try:
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
        
        # Generate theme ID
        theme_id = str(uuid.uuid4())
        
        # Create theme record
        theme_metadata = {
            'id': theme_id,
            'title': theme_name,
            'description': style_description or f"Theme uploaded on {datetime.utcnow().isoformat()}",
            'status': 'active',
            'content': content_str,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Store theme in database
        supabase.table('themes').insert(theme_metadata).execute()
        
        # Process theme to extract and store all elements
        extractor = FixedElementorExtractor()
        theme_id, pages_data, sections_data = extractor.process_theme(theme_id)
        
        return {
            "message": f"Successfully stored theme {theme_name}",
            "theme_id": theme_id,
            "pages_count": len(pages_data),
            "sections_count": len(sections_data)
        }
            
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error storing theme: {str(e)}")


@app.post("/evaluate/sections")
async def evaluate_theme_sections(request: SectionEvaluationRequest):
    """Evaluate and categorize all sections in a theme using enhanced Elementor data analysis"""
    try:
        # Log the request
        logging.info(f"Received section evaluation request for theme ID: {request.theme_id}")
        logging.info(f"Using enhanced Elementor data analysis for more accurate section categorization")
        
        # Validate theme ID
        if not request.theme_id:
            raise HTTPException(status_code=400, detail="Theme ID is required")
            
        # Evaluate sections
        result = orchestrator.section_evaluator.evaluate_theme_sections(request.theme_id)
        
        # Add detailed analysis information to the response
        result["detailed_analysis_used"] = request.detailed_analysis
        result["evaluated_at"] = datetime.utcnow().isoformat()
        
        return JSONResponse(content=result)
        
    except ValueError as e:
        logging.error(f"Value error in section evaluation: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error evaluating sections: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error evaluating sections: {str(e)}")
        


@app.post("/recreate-theme")
async def recreate_theme(
    request: RecreateThemeRequest,
    background_tasks: BackgroundTasks
):
    """Recreate a theme by filtering unique pages and transforming content"""
    try:
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'source_theme_id': request.theme_id,
            'style_description': request.style_description,
            'replace_images': request.replace_images,
            'gbp_object': request.google_data
        }
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        if not supabase_url or not supabase_key:
            raise HTTPException(status_code=500, detail="SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        supabase = create_client(supabase_url, supabase_key)
        theme_result = supabase.table('themes').select('*').eq('id', request.theme_id).execute()
        if not theme_result.data:
            raise HTTPException(status_code=404, detail=f"Theme with ID '{request.theme_id}' not found")
        theme_data = theme_result.data[0]
        xml_content = theme_data.get('content')
        if not xml_content:
            raise HTTPException(status_code=400, detail="No XML content found in theme")
        work_dir = os.path.join(orchestrator.base_dir, "processing", job_id)
        os.makedirs(work_dir, exist_ok=True)
        input_path = os.path.join(work_dir, f"input_{request.theme_id}.xml")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        filtered_xml = orchestrator.filter_unique_pages(xml_content)
        filtered_path = os.path.join(work_dir, f"filtered_{request.theme_id}.xml")
        with open(filtered_path, "w", encoding="utf-8") as f:
            f.write(filtered_xml)
        background_tasks.add_task(
            orchestrator.process_theme,
            job_id,
            filtered_path,
            request.style_description,
            True,  # skip_theme_creation
            request.replace_images,  # Pass replace_images
            request.google_data
        )
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Theme recreation started'
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error recreating theme: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/color-mapping")
async def get_color_mapping(request: ColorMappingRequest):
    """Get the Elementor color properties mapping for a job"""
    try:
        # Check if job exists
        if request.job_id not in orchestrator.jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job = orchestrator.jobs[request.job_id]
        
        # Check if job has style_description
        if 'style_description' not in job:
            raise HTTPException(status_code=400, detail="Job does not have style information")
        
        style_description = job['style_description']
        
        # Generate color palette and mapping using GPT-4o if available
        try:
            # First try to generate a palette and mapping with GPT-4o
            palette, custom_mapping = generate_color_palette_with_gpt4o(style_description)
            # Map colors to Elementor properties using custom mapping if available
            elementor_colors = map_colors_to_elementor(palette, custom_mapping)
        except Exception as e:
            # Fall back to algorithmic method if GPT-4o fails
            logging.warning(f"Falling back to algorithmic color palette generation: {str(e)}")
            primary_color = extract_color_from_description(style_description)
            palette = generate_color_palette(primary_color)
            elementor_colors = map_colors_to_elementor(palette)
        
        return JSONResponse(content={
            "job_id": request.job_id,
            "style_description": style_description,
            "elementor_colors": elementor_colors
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error getting color mapping: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting color mapping: {str(e)}")

@app.post("/page-info")
async def get_page_info(request: PageInfoRequest):
    """Get page IDs and slugs for a job"""
    try:
        # Check if job exists
        if request.job_id not in orchestrator.jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job = orchestrator.jobs[request.job_id]
        
        # Check if job has completed
        if job['status'] != 'completed':
            raise HTTPException(status_code=400, detail="Job has not completed yet")
        
        # Determine if it's a one-page or multi-page site
        job_type = job.get('job_type', 'unknown')
        
        # Construct the output path based on job ID
        output_path = os.path.join(orchestrator.base_dir, "output", f"{request.job_id}.xml")
        if not os.path.exists(output_path):
            raise HTTPException(status_code=404, detail="Output file not found")
        
        # Parse the XML to extract page information
        tree = ET.parse(output_path)
        root = tree.getroot()
        
        # Find all items (pages)
        items = root.findall(".//item")
        
        # Extract page information
        pages_info = []
        for item in items:
            # Get post type
            post_type = item.find("./wp:post_type", {"wp": "http://wordpress.org/export/1.2/"})
            if post_type is not None and post_type.text == "page":
                # Get page ID
                post_id = item.find("./wp:post_id", {"wp": "http://wordpress.org/export/1.2/"})
                # Get page slug (post_name)
                post_name = item.find("./wp:post_name", {"wp": "http://wordpress.org/export/1.2/"})
                # Get page title
                title = item.find("./title")
                
                if post_id is not None and post_name is not None:
                    pages_info.append({
                        "id": post_id.text,
                        "slug": post_name.text,
                        "title": title.text if title is not None else ""
                    })
        
        return JSONResponse(content={
            "job_id": request.job_id,
            "job_type": job_type,
            "pages": pages_info
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error getting page information: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting page information: {str(e)}")

@app.post("/validate-google-data")
async def validate_google_data(google_data: dict):
    """Validate and process a Google Business Profile object"""
    try:
        # Process the google_data object
        business_info = process_gbp_object(google_data)
        preservation_prompt = create_gbp_preservation_prompt(business_info)
        
        return {
            "valid": True,
            "business_info": business_info,
            "preservation_prompt": preservation_prompt,
            "business_name": business_info.get("business_name", ""),
            "address": business_info.get("address", ""),
            "phone": business_info.get("phone", ""),
            "website": business_info.get("website", ""),
            "rating": business_info.get("rating", 0),
            "total_reviews": business_info.get("total_reviews", 0),
            "opening_hours": business_info.get("opening_hours", {}),
            "photos_count": len(business_info.get("photos", [])),
            "reviews_count": len(business_info.get("reviews", [])),
            "geometry": business_info.get("geometry", {}),
            "place_id": business_info.get("place_id", ""),
            "status": business_info.get("status", "")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid google_data: {str(e)}")

@app.post("/google-data-preview")
async def preview_google_data_transformation(
    style_description: str,
    google_data: dict
):
    """Preview how google_data would be processed with a given style description"""
    try:
        # Process the google_data object
        business_info = process_gbp_object(google_data)
        preservation_prompt = create_gbp_preservation_prompt(business_info)
        
        # Combine style description with preservation prompt
        final_style_description = f"{style_description}\n\n{preservation_prompt}"
        
        return {
            "original_style_description": style_description,
            "final_style_description": final_style_description,
            "business_info": business_info,
            "preservation_prompt": preservation_prompt,
            "preserved_elements": {
                "business_name": business_info.get("business_name"),
                "address": business_info.get("address"),
                "phone": business_info.get("phone"),
                "website": business_info.get("website"),
                "opening_hours": business_info.get("opening_hours", {}).get("weekday_text", []),
                "photos_count": len(business_info.get("photos", [])),
                "reviews_count": len(business_info.get("reviews", []))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing google_data preview: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
