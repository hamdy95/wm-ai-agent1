from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import uuid
import shutil
import os
import sys
from datetime import datetime
import json
import xml.etree.ElementTree as ET
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

# Handle imports differently based on how script is run
try:
    # When imported as a module
    from offline.agentoff import FixedElementorExtractor, ThemeTransformByIdRequest
    from offline.transformation import ContentTransformationAgent
    from offline.onepage_agent import OnePageSiteGenerator
    from offline.multipage_agent import MultiPageSiteGenerator
    from offline.evaluator_agent import SectionEvaluator
    from offline.color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping, generate_color_palette_with_gpt4o
except ImportError:
    # When run directly
    from agentoff import FixedElementorExtractor, ThemeTransformByIdRequest
    from transformation import ContentTransformationAgent
    from onepage_agent import OnePageSiteGenerator
    from multipage_agent import MultiPageSiteGenerator
    from evaluator_agent import SectionEvaluator
    from color_utils import extract_color_from_description, generate_color_palette, map_colors_to_elementor, create_color_mapping, generate_color_palette_with_gpt4o

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

class StyleDescription(BaseModel):
    description: str
    replace_images: Optional[bool] = False

class SiteGenerationRequest(BaseModel):
    query: str
    style_description: Optional[str] = "modern professional style with clean design"
    replace_images: Optional[bool] = False

class ThemeIdTransformation(BaseModel):
    theme_id: str
    style_description: str
    replace_images: Optional[bool] = False

class RecreateThemeRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None
    replace_images: Optional[bool] = False

class EvaluateSectionsRequest(BaseModel):
    theme_id: str
    detailed_analysis: Optional[bool] = True

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
        return "<![CDATA[{}]]>".format(self.text)

# Add helper function for CDATA in ElementTree
ET._original_serialize_xml = ET._serialize_xml

def _serialize_xml(write, elem, qnames, namespaces, **kwargs):
    if elem.text.__class__.__name__ == "CDATA":
        write("<{}".format(qnames[elem.tag]))
        items = list(elem.items())
        if items:
            items.sort()
            for name, value in items:
                write(' {}="{}"'.format(qnames[name], xml_escape(value)))
        write(">")
        write(str(elem.text))
        write("</{}>".format(qnames[elem.tag]))
        if elem.tail:
            write(xml_escape(elem.tail))
    else:
        return ET._original_serialize_xml(write, elem, qnames, namespaces, **kwargs)
        
ET._serialize_xml = _serialize_xml

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

    
    def process_theme(self, job_id: str, input_path: str, style_description: str, skip_theme_creation: bool = False, replace_images: bool = False):
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
            
            # Step 2: Transform content
            print(f"Transforming content with style: {style_description}...")
            transformation_result = self.transformation_agent.transform_theme_content(
                theme_id or job_id,
                style_description,
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
                        'created_at': datetime.utcnow().isoformat()
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

    def generate_one_page_site(self, job_id: str, query: str, style_description: str = None, replace_images: bool = False):
        """Generate a one-page site from user query"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        try:
            self.jobs[job_id]["status"] = "processing"
            os.makedirs(work_dir, exist_ok=True)
            print(f"Generating one-page site from query: {query}...")
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
            transformation_result = self.transformation_agent.transform_theme_content(theme_id, combined_query)
            if 'text_transformations' not in transformation_result:
                transformation_result['text_transformations'] = []
            if 'color_palette' not in transformation_result:
                transformation_result['color_palette'] = {'original_colors': [], 'new_colors': []}
            elif isinstance(transformation_result['color_palette'], dict):
                if 'color_palette' in transformation_result['color_palette']:
                    transformation_result['color_palette'] = transformation_result['color_palette']['color_palette']
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
                        'combined_query': combined_query
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

    def generate_multi_page_site(self, job_id: str, query: str, style_description: str = None, replace_images: bool = False):
        """Generate a multi-page site from user query"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        try:
            self.jobs[job_id]["status"] = "processing"
            os.makedirs(work_dir, exist_ok=True)
            print(f"Generating multi-page site from query: {query}...")
            temp_output_path = os.path.join(work_dir, "multipage_temp.xml")
            combined_query = query
            if style_description and style_description.strip():
                combined_query = f"{query} with {style_description}"
            try:
                self.multipage_generator.create_multi_page_site(combined_query, temp_output_path, style_description)
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
            print(f"Applying style: {combined_query}...")
            transformation_result = self.transformation_agent.transform_theme_content(theme_id, combined_query)
            if 'text_transformations' not in transformation_result:
                transformation_result['text_transformations'] = []
            if 'color_palette' not in transformation_result:
                transformation_result['color_palette'] = {'original_colors': [], 'new_colors': []}
            elif isinstance(transformation_result['color_palette'], dict):
                if 'color_palette' in transformation_result['color_palette']:
                    transformation_result['color_palette'] = transformation_result['color_palette']['color_palette']
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
                        'combined_query': combined_query
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

    def process_theme_by_id(self, job_id: str, theme_id: str, style_description: str, replace_images: bool = False):
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
                extracted_theme_id, pages_data, sections_data = self.extraction_agent.process_theme(input_path)
                print(f"Transforming content with style: {style_description or 'default style'}...")
                transformation_result = self.transformation_agent.transform_theme_content(
                    extracted_theme_id,
                    style_description or ""
                )
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
                    'created_at': datetime.utcnow().isoformat()
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

class ThemeTransformByIdRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None
    replace_images: Optional[bool] = False

class ThemeGenerateRequest(BaseModel):
    style_description: str
    page_count: Optional[int] = 1

class ThemeStoreRequest(BaseModel):
    theme_name: str
    style_description: Optional[str] = None

class SectionEvaluationRequest(BaseModel):
    theme_id: str
    detailed_analysis: Optional[bool] = True

# Define request models for site generation
class OnePageSiteRequest(BaseModel):
    query: str = Field(..., description="The description of sections to include in the site, e.g., 'hero, about, services, contact'")
    style_description: Optional[str] = "modern professional style with clean design"
    replace_images: Optional[bool] = False

class MultiPageSiteRequest(BaseModel):
    query: str = Field(..., description="The description of pages to include in the site, e.g., 'home, about, services, contact'")
    style_description: Optional[str] = "modern professional style with clean design"
    replace_images: Optional[bool] = False

# Initialize orchestrator
orchestrator = ThemeTransformerOrchestrator()

@app.post("/transform")
async def transform_theme(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    style_description: str = Form(...),
    replace_images: bool = Form(False)
):
    """Transform a WordPress theme file with the given style description"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        # Create job record
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'source_file': file.filename,
            'style_description': style_description,
            'replace_images': replace_images
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
            replace_images  # Add replace_images parameter
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
            'replace_images': request.replace_images
        }
        
        # Start generation in background
        background_tasks.add_task(
            orchestrator.generate_one_page_site,
            job_id,
            request.query,
            request.style_description,
            request.replace_images  # Pass replace_images parameter
        )
        
        return TransformationResponse(
            job_id=job_id,
            status='queued',
            created_at=created_at,
            message='Single-page theme generation started'
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
            'replace_images': request.replace_images
        }
        
        # Start generation in background
        background_tasks.add_task(
            orchestrator.generate_multi_page_site,
            job_id,
            request.query,
            request.style_description,
            request.replace_images  # Pass replace_images
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
    return {
        'job_id': job_id,
        'status': job['status'],
        'created_at': job['created_at'],
        'completed_at': job.get('completed_at'),
        'error': job.get('error')
    }

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
            'replace_images': request.replace_images
        }
        
        # Start transformation in background
        background_tasks.add_task(
            orchestrator.process_theme_by_id,
            job_id,
            request.theme_id,
            request.style_description,
            request.replace_images  # Pass replace_images
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
            'replace_images': request.replace_images
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
            request.replace_images  # Pass replace_images
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
