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
from replace import replace_text_and_colors
import logging

# Create FastAPI app instance at module level
app = FastAPI(
    title="WordPress Theme Transformer API",
    description="API for transforming WordPress themes with Elementor",
    version="1.0.0"
)

# Handle imports differently based on how script is run
try:
    # When imported as a module
    from offline.agentoff import FixedElementorExtractor, ThemeTransformByIdRequest
    from offline.transformation import ContentTransformationAgent
    from offline.onepage_agent import OnePageSiteGenerator
    from offline.multipage_agent import MultiPageSiteGenerator
except ImportError:
    # When run directly
    from agentoff import FixedElementorExtractor, ThemeTransformByIdRequest
    from transformation import ContentTransformationAgent
    from onepage_agent import OnePageSiteGenerator
    from multipage_agent import MultiPageSiteGenerator

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

class SiteGenerationRequest(BaseModel):
    query: str
    style_description: Optional[str] = "modern professional style with clean design"

class ThemeIdTransformation(BaseModel):
    theme_id: str
    style_description: str

class RecreateThemeRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None

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
        except ImportError:
            # When run directly
            from agentoff import FixedElementorExtractor
            from transformation import ContentTransformationAgent
            from onepage_agent import OnePageSiteGenerator
            from multipage_agent import MultiPageSiteGenerator
        
        self.extraction_agent = FixedElementorExtractor()
        self.transformation_agent = ContentTransformationAgent()
        self.onepage_generator = OnePageSiteGenerator()
        self.multipage_generator = MultiPageSiteGenerator()
        
        # Create work directories
        for dir_name in ["input", "processing", "output"]:
            dir_path = os.path.join(self.base_dir, dir_name)
            os.makedirs(dir_path, exist_ok=True)

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

    
    def process_theme(self, job_id: str, input_path: str, style_description: str, skip_theme_creation: bool = False):
        """Process theme transformation"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        theme_id = None
        
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

    def generate_one_page_site(self, job_id: str, query: str, style_description: str = None):
        """Generate a one-page site from user query"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        
        try:
            # Update job status
            self.jobs[job_id]["status"] = "processing"
            
            # Create job working directory
            os.makedirs(work_dir, exist_ok=True)
            
            # Step 1: Generate one-page site
            print(f"Generating one-page site from query: {query}...")
            temp_output_path = os.path.join(work_dir, "onepage_temp.xml")
            
            # Combine query and style_description if both are provided
            combined_query = query
            if style_description and style_description.strip():
                combined_query = f"{query} with {style_description}"
                
            try:
                self.onepage_generator.create_one_page_site(combined_query, temp_output_path)
            except Exception as e:
                raise ValueError(f"Error generating one-page site: {str(e)}")
            
            # Verify the generated file is valid XML
            if not self.validate_xml(temp_output_path):
                raise ValueError("Generated one-page site XML is invalid")
            
            # Step 2: Transform the site with the query/style description
            # Extract content first
            print(f"Extracting content from generated site...")
            try:
                theme_id, pages_data, sections_data = self.extraction_agent.process_theme(temp_output_path)
            except ET.ParseError as e:
                raise ValueError(f"XML parsing error: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error during extraction: {str(e)}")
            
            # Transform content
            print(f"Applying style: {combined_query}...")
            transformation_result = self.transformation_agent.transform_theme_content(theme_id, combined_query)
            
            # Save transformation
            transformed_path = os.path.join(work_dir, f"transformed_{theme_id}.json")
            with open(transformed_path, 'w', encoding='utf-8') as f:
                json.dump(transformation_result, f, ensure_ascii=False, indent=2)
            
            # Apply transformations
            output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
            replace_text_and_colors(
                temp_output_path,
                transformed_path,
                output_path
            )
            
            # Validate output
            if not self.validate_xml(output_path):
                raise Exception("Output XML validation failed - the generated file is not a valid XML document")
            
            # Update job status
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
            # Cleanup processing directory if it exists
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")
    
    def generate_multi_page_site(self, job_id: str, query: str, style_description: str = None):
        """Generate a multi-page site from user query"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        
        try:
            # Update job status
            self.jobs[job_id]["status"] = "processing"
            
            # Create job working directory
            os.makedirs(work_dir, exist_ok=True)
            
            # Step 1: Generate multi-page site
            print(f"Generating multi-page site from query: {query}...")
            temp_output_path = os.path.join(work_dir, "multipage_temp.xml")
            
            # Combine query and style_description if both are provided
            combined_query = query
            if style_description and style_description.strip():
                combined_query = f"{query} with {style_description}"
                
            try:
                self.multipage_generator.create_multi_page_site(combined_query, temp_output_path)
            except Exception as e:
                raise ValueError(f"Error generating multi-page site: {str(e)}")
            
            # Verify the generated file is valid XML
            if not self.validate_xml(temp_output_path):
                raise ValueError("Generated multi-page site XML is invalid")
            
            # Step 2: Transform the site with the query/style description
            # Extract content first
            print(f"Extracting content from generated site...")
            try:
                theme_id, pages_data, sections_data = self.extraction_agent.process_theme(temp_output_path)
            except ET.ParseError as e:
                # Save the problematic XML file for debugging
                debug_path = os.path.join(self.base_dir, "output", f"debug_{job_id}.xml")
                shutil.copy(temp_output_path, debug_path)
                raise ValueError(f"XML parsing error in {debug_path}: {str(e)}")
            except Exception as e:
                raise ValueError(f"Error during extraction: {str(e)}")
            
            # Transform content
            print(f"Applying style: {combined_query}...")
            transformation_result = self.transformation_agent.transform_theme_content(theme_id, combined_query)
            
            # Save transformation
            transformed_path = os.path.join(work_dir, f"transformed_{theme_id}.json")
            with open(transformed_path, 'w', encoding='utf-8') as f:
                json.dump(transformation_result, f, ensure_ascii=False, indent=2)
            
            # Apply transformations
            output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
            replace_text_and_colors(
                temp_output_path,
                transformed_path,
                output_path
            )
            
            # Validate output
            if not self.validate_xml(output_path):
                raise Exception("Output XML validation failed - the generated file is not a valid XML document")
            
            # Update job status
            self.jobs[job_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "output_url": f"/download/{job_id}",
                "job_type": "multi_page_site"
            })
            
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
            # Cleanup processing directory if it exists
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")

    def download_theme_from_url(self, url: str, output_path: str) -> bool:
        """Download theme XML from URL"""
        try:
            import requests
            print(f"Downloading theme from URL: {url}")
            
            # Make the request
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            # Check if the response looks like XML
            content = response.text
            if not (content.strip().startswith('<?xml') or content.strip().startswith('<')):
                print(f"Warning: Downloaded content may not be valid XML. Content starts with: {content[:100]}...")
            
            # Save the content
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            print(f"Successfully downloaded theme to: {output_path}")
            return True
        except Exception as e:
            print(f"Error downloading theme: {e}")
            return False

    def transform_theme_by_id(self, theme_id, style_description=None):
        """Transform a theme by its ID from the database"""
        try:
            # Validate and convert the input to a proper UUID string
            try:
                valid_theme_id = str(uuid.UUID(theme_id))
            except ValueError:
                error_message = f"Provided theme_id '{theme_id}' is not a valid UUID."
                logging.error(error_message)
                return {"error": error_message}
                
            print(f"Starting transformation for theme ID: {valid_theme_id}")
            
            # Get Supabase credentials
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            
            if not supabase_url or not supabase_key:
                return {"error": "SUPABASE_URL and SUPABASE_KEY must be set in .env file"}
                
            supabase = create_client(supabase_url, supabase_key)
            
            # Check if there's existing transformation data for this theme
            transformation_data = None
            if not style_description:
                # If no new style description, try to use existing transformation data
                try:
                    trans_result = supabase.table('transformation_data').select('*').eq('theme_id', valid_theme_id).execute()
                    if trans_result.data:
                        transformation_data = trans_result.data[0]
                        print(f"Found existing transformation data for theme {valid_theme_id}")
                except Exception as e:
                    print(f"Error fetching transformation data: {e}")
            
            # Initialize theme_data
            theme_data = {}
            
            # Get theme information
            try:
                theme_result = supabase.table('themes').select('*').eq('id', valid_theme_id).execute()
                if not theme_result.data:
                    return {"error": f"Theme with ID '{valid_theme_id}' not found in database"}
                theme_data = theme_result.data[0]
                print(f"Retrieved theme data: {theme_data.get('title', 'Unknown')}")
            except Exception as e:
                return {"error": f"Error retrieving theme data: {str(e)}"}
                
            # Create temporary directory for processing
            temp_dir = "processing"
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate paths for temp files
            timestamp = int(time.time())
            input_path = os.path.join(temp_dir, f"input_{valid_theme_id}_{timestamp}.xml")
            transformed_json_path = os.path.join(temp_dir, f"transformed_{valid_theme_id}_{timestamp}.json")
            new_theme_path = os.path.join(temp_dir, f"new_theme_{valid_theme_id}_{timestamp}.xml")
            
            # Check for XML content in theme_data
            xml_content = None
            for field in ['content', 'xml_content', 'xml_data', 'file_content', 'theme_content', 'data']:
                if field in theme_data and theme_data.get(field):
                    xml_content = theme_data.get(field)
                    print(f"Found XML content in field '{field}'")
                    break
            
            # If no XML content, return error
            if not xml_content:
                return {"error": "No XML content found in the theme data"}
            
            # Write XML content to temporary file
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
                
            print(f"Wrote source XML to {input_path}")
            
            # First extract content from the XML
            print(f"Extracting content from theme XML")
            try:
                extracted_theme_id, pages_data, sections_data = self.extraction_agent.process_theme(input_path)
            except Exception as e:
                print(f"Error extracting content: {e}")
                return {"error": f"Failed to extract content from theme: {str(e)}"}
            
            # Generate transformation for the extracted content
            print(f"Generating transformation with style: {style_description or 'default style'}")
            try:
                transformation_result = self.transformation_agent.transform_theme_content(
                    extracted_theme_id, 
                    style_description or ""
                )
                
                # Save transformation data to file
                with open(transformed_json_path, 'w', encoding='utf-8') as f:
                    json.dump(transformation_result, f, indent=2)
            except Exception as e:
                print(f"Error generating transformation: {e}")
                return {"error": f"Failed to generate transformation: {str(e)}"}
                
            # Apply transformations
            print(f"Applying transformation to XML content")
            
            try:
                # Apply transformation to the XML
                replace_text_and_colors(
                    source_xml_path_or_id=input_path,
                    transformations_json_path=transformed_json_path,
                    output_xml_path=new_theme_path
                )
                
                # Read the transformed XML
                with open(new_theme_path, 'r', encoding='utf-8') as f:
                    transformed_xml = f.read()
                
                # Store the transformed XML back in the database as a new theme
                new_theme_id = str(uuid.uuid4())
                new_theme_record = {
                    'id': new_theme_id,
                    'title': f"Transformed {theme_data.get('title', 'Theme')}",
                    'description': f"Transformed from theme {valid_theme_id} with style '{style_description or 'default'}'",
                    'content': transformed_xml,
                    'status': 'active',
                    'created_at': datetime.utcnow().isoformat()
                }
                
                supabase.table('themes').insert(new_theme_record).execute()
                print(f"Stored transformed theme in database with ID: {new_theme_id}")
                
                # Store the transformation data in the database
                transformation_id = str(uuid.uuid4())
                
                # Extract text transformations and colors from transformation result
                text_transformations = transformation_result.get('text_transformations', [])
                color_palette = transformation_result.get('color_palette', {})
                
                transformation_record = {
                    'id': transformation_id,
                    'theme_id': valid_theme_id,
                    'texts': text_transformations,
                    'colors': color_palette.get('new_colors', []),
                    'created_at': datetime.utcnow().isoformat()
                }
                
                # Save debug information
                debug_path = os.path.join(temp_dir, f"transformation_debug_{valid_theme_id}_{timestamp}.json")
                with open(debug_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'transformation_result': transformation_result,
                        'transformation_record': transformation_record
                    }, f, indent=2)
                
                supabase.table('transformation_data').insert(transformation_record).execute()
                print(f"Stored transformation data in database with ID: {transformation_id}")
                
            except Exception as e:
                print(f"Error during transformation: {e}")
                traceback.print_exc()
                return {"error": f"Failed to transform theme: {str(e)}"}
            
            # Clean up temporary files
            try:
                for file_path in [input_path, transformed_json_path, new_theme_path]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Removed temporary file: {file_path}")
            except Exception as e:
                print(f"Error cleaning up temporary files: {e}")
            
            return {
                "original_theme_id": valid_theme_id,
                "new_theme_id": new_theme_id,
                "message": "Theme transformed successfully with new transformation data",
                "transformation_data_id": transformation_id
            }
                
        except Exception as e:
            traceback.print_exc()
            return {"error": f"Error transforming theme: {str(e)}"}

    def _generate_minimal_template(self, template_path, theme_title="Generated Theme"):
        """Generate a comprehensive WordPress theme XML template with proper structure"""
        
        # Define basic site information
        site_title = theme_title 
        site_link = "https://example.com"
        site_description = "A generated WordPress theme"
        pub_date = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
        language = "en-US"
        
        # Create the root structure
        root = ET.Element("rss")
        root.set("version", "2.0")
        root.set("xmlns:excerpt", "http://wordpress.org/export/1.2/excerpt/")
        root.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
        root.set("xmlns:wfw", "http://wellformedweb.org/CommentAPI/")
        root.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
        root.set("xmlns:wp", "http://wordpress.org/export/1.2/")
        
        # Channel element
        channel = ET.SubElement(root, "channel")
        
        # Add site info
        ET.SubElement(channel, "title").text = site_title
        ET.SubElement(channel, "link").text = site_link
        ET.SubElement(channel, "description").text = site_description
        ET.SubElement(channel, "pubDate").text = pub_date
        ET.SubElement(channel, "language").text = language
        ET.SubElement(channel, "wp:wxr_version").text = "1.2"
        ET.SubElement(channel, "wp:base_site_url").text = site_link
        ET.SubElement(channel, "wp:base_blog_url").text = site_link
        
        # Add generator info
        ET.SubElement(channel, "generator").text = "WordPress Agent Generator 1.0"
        
        # Add template pages
        self._add_template_page(channel, "Home", "homepage", "publish", "page")
        self._add_template_page(channel, "About", "about", "publish", "page")
        self._add_template_page(channel, "Contact", "contact", "publish", "page")
        self._add_template_page(channel, "Blog", "blog", "publish", "page")
        self._add_template_page(channel, "Services", "services", "publish", "page")
        
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(template_path)), exist_ok=True)
        
        # Write the template to file with proper XML declaration
        with open(template_path, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            tree = ET.ElementTree(root)
            tree.write(f, encoding='UTF-8', xml_declaration=False)
            
        print(f"Generated comprehensive WordPress theme template at: {template_path}")
        
    def _add_template_page(self, channel, title, slug, status="publish", post_type="page"):
        """Add a template page to the WordPress XML"""
        item = ET.SubElement(channel, "item")
        
        # Basic page info
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = f"https://example.com/{slug}/"
        ET.SubElement(item, "pubDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
        ET.SubElement(item, "dc:creator").text = "admin"
        ET.SubElement(item, "guid", isPermaLink="false").text = f"https://example.com/{slug}/"
        ET.SubElement(item, "description").text = ""
        
        # Content - include Elementor placeholder data
        content_text = f"""<!-- wp:paragraph -->
<p>This is a {title.lower()} page template. Replace with your content.</p>
<!-- /wp:paragraph -->

<!-- wp:elementor/elementor {{"content":"<div data-elementor-type=\\"wp-page\\" data-elementor-id=\\"123\\" class=\\"elementor elementor-123\\">Elementor content placeholder</div>"}} -->
<div class="elementor-placeholder">Elementor {title} Template</div>
<!-- /wp:elementor/elementor -->"""
        
        ET.SubElement(item, "content:encoded").text = CDATA(content_text)
        ET.SubElement(item, "excerpt:encoded").text = CDATA("")
        
        # WordPress specific elements
        ET.SubElement(item, "wp:post_id").text = str(random.randint(1000, 9999))
        ET.SubElement(item, "wp:post_date").text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ET.SubElement(item, "wp:post_date_gmt").text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ET.SubElement(item, "wp:post_modified").text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ET.SubElement(item, "wp:post_modified_gmt").text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ET.SubElement(item, "wp:comment_status").text = "closed"
        ET.SubElement(item, "wp:ping_status").text = "closed"
        ET.SubElement(item, "wp:post_name").text = slug
        ET.SubElement(item, "wp:status").text = status
        ET.SubElement(item, "wp:post_type").text = post_type
        ET.SubElement(item, "wp:post_parent").text = "0"
        ET.SubElement(item, "wp:menu_order").text = "0"
        
        # Add Elementor metadata
        postmeta = ET.SubElement(item, "wp:postmeta")
        ET.SubElement(postmeta, "wp:meta_key").text = "_elementor_edit_mode"
        ET.SubElement(postmeta, "wp:meta_value").text = CDATA("builder")
        
        postmeta2 = ET.SubElement(item, "wp:postmeta")
        ET.SubElement(postmeta2, "wp:meta_key").text = "_elementor_template_type"
        ET.SubElement(postmeta2, "wp:meta_value").text = CDATA("wp-page")
        
        postmeta3 = ET.SubElement(item, "wp:postmeta")
        ET.SubElement(postmeta3, "wp:meta_key").text = "_wp_page_template"
        ET.SubElement(postmeta3, "wp:meta_value").text = CDATA("default")
        
        return item

    def process_theme_by_id(self, job_id: str, theme_id: str, style_description: str):
        """Process a theme transformation by its ID"""
        work_dir = os.path.join(self.base_dir, "processing", job_id)
        output_path = os.path.join(self.base_dir, "output", f"{job_id}.xml")
        
        try:
            # Validate and convert theme_id to a proper UUID string
            try:
                valid_theme_id = str(uuid.UUID(theme_id))
            except ValueError:
                raise ValueError(f"Provided theme_id '{theme_id}' is not a valid UUID.")
            
            # Update job status
            self.jobs[job_id]["status"] = "processing"
            
            # Create job working directory
            os.makedirs(work_dir, exist_ok=True)
            
            # Get Supabase credentials
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            
            if not supabase_url or not supabase_key:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
                
            supabase = create_client(supabase_url, supabase_key)
            
            # Check if there's existing transformation data for this theme
            transformation_data = None
            if not style_description:
                try:
                    trans_result = supabase.table('transformation_data').select('*').eq('theme_id', valid_theme_id).execute()
                    if trans_result.data:
                        transformation_data = trans_result.data[0]
                        print(f"Found existing transformation data for theme {valid_theme_id}")
                except Exception as e:
                    print(f"Error fetching transformation data: {e}")
            
            # Get theme information using the validated theme_id
            theme_result = supabase.table('themes').select('*').eq('id', valid_theme_id).execute()
            if not theme_result.data:
                raise ValueError(f"Theme with ID '{valid_theme_id}' not found in database")
                
            theme_data = theme_result.data[0]
            
            # Check for XML content
            xml_content = None
            for field in ['content', 'xml_content', 'xml_data', 'file_content', 'theme_content', 'data']:
                if field in theme_data and theme_data.get(field):
                    xml_content = theme_data.get(field)
                    break
                    
            if not xml_content:
                raise ValueError(f"No XML content found for theme ID '{valid_theme_id}'")
            
            # Save XML content to a file
            input_path = os.path.join(work_dir, f"input_{valid_theme_id}.xml")
            with open(input_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
                
            print(f"Saved theme XML to {input_path}")
            
            # Update job record with file paths, etc.
            self.jobs[job_id].update({
                "theme_id": valid_theme_id,
                "theme_title": theme_data.get('title', 'Unknown theme'),
                "input_path": input_path,
                "output_path": output_path
            })
            
            # Validate input XML
            if not self.validate_xml(input_path):
                raise ValueError(f"Invalid XML content for theme ID: {valid_theme_id}")
            
            # Step 1: Extract content
            print(f"Extracting content from theme ID: {valid_theme_id}...")
            try:
                extracted_theme_id, pages_data, sections_data = self.extraction_agent.process_theme(input_path)
            except Exception as e:
                raise ValueError(f"Error during extraction: {str(e)}")
            
            # Step 2: Transform content
            print(f"Transforming content with style: {style_description or 'default style'}...")
            transformation_result = self.transformation_agent.transform_theme_content(
                extracted_theme_id,
                style_description or ""
            )
            
            # Save transformation data
            transformation_path = os.path.join(work_dir, f"transformation_{valid_theme_id}.json")
            with open(transformation_path, 'w', encoding='utf-8') as f:
                json.dump(transformation_result, f, indent=2)
            
            # Step 3: Apply transformations to generate new theme
            print(f"Applying transformations to generate new theme...")
            replace_text_and_colors(
                input_path,
                transformation_path,
                output_path
            )
            
            # Update job status
            self.jobs[job_id].update({
                "status": "completed", 
                "completed_at": datetime.utcnow().isoformat(),
                "output_url": f"/download/{job_id}"
            })
            
            # Store transformation data in Supabase
            try:
                # Store transformation data
                transformation_id = str(uuid.uuid4())
                
                # Extract text transformations and colors
                text_transformations = transformation_result.get('text_transformations', [])
                color_palette = transformation_result.get('color_palette', {})
                
                transformation_data = {
                    'id': transformation_id,
                    'theme_id': valid_theme_id,
                    'texts': text_transformations,
                    'colors': color_palette.get('new_colors', []),
                    'created_at': datetime.utcnow().isoformat()
                }
                
                # Write debug info to help diagnose transformation issues
                debug_dir = os.path.join(os.path.dirname(output_path), "debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, "transformation_debug.json"), 'w', encoding='utf-8') as f:
                    json.dump({
                        'raw_transformation': transformation_result,
                        'stored_transformation': transformation_data
                    }, f, indent=2, ensure_ascii=False)
                
                # Insert transformation data
                supabase.table('transformation_data').insert(transformation_data).execute()
                print(f"Stored transformation data with ID: {transformation_id}")
                print(f"Saved {len(text_transformations)} transformed texts and {len(color_palette.get('new_colors', []))} colors")
            except Exception as e:
                print(f"Failed to store transformation data: {e}")
            
            # Validate output
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
            # Cleanup work directory
            if os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    print(f"Failed to cleanup work directory: {e}")

# Define request models
class ThemeTransformRequest(BaseModel):
    style_description: str

class ThemeTransformByIdRequest(BaseModel):
    theme_id: str
    style_description: Optional[str] = None

class ThemeGenerateRequest(BaseModel):
    style_description: str
    page_count: Optional[int] = 1

class ThemeStoreRequest(BaseModel):
    theme_name: str
    style_description: Optional[str] = None

# Define request models for site generation
class OnePageSiteRequest(BaseModel):
    query: str = Field(..., description="The description of sections to include in the site, e.g., 'hero, about, services, contact'")
    style_description: Optional[str] = "modern professional style with clean design"

class MultiPageSiteRequest(BaseModel):
    query: str = Field(..., description="The description of pages to include in the site, e.g., 'home, about, services, contact'")
    style_description: Optional[str] = "modern professional style with clean design"

# Initialize orchestrator
orchestrator = ThemeTransformerOrchestrator()

@app.post("/transform")
async def transform_theme(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    style_description: str = Form(...)
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
            'style_description': style_description
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
            style_description
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
            'type': 'onepage'
        }
        
        # Start generation in background
        background_tasks.add_task(
            orchestrator.generate_one_page_site,
            job_id,
            request.query,
            request.style_description
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
            'type': 'multipage'
        }
        
        # Start generation in background
        background_tasks.add_task(
            orchestrator.generate_multi_page_site,
            job_id,
            request.query,
            request.style_description
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
            'style_description': request.style_description
        }
        
        # Start transformation in background
        background_tasks.add_task(
            orchestrator.process_theme_by_id,
            job_id,
            request.theme_id,
            request.style_description
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
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        # Create job record
        orchestrator.jobs[job_id] = {
            'id': job_id,
            'status': 'queued',
            'created_at': created_at,
            'source_theme_id': request.theme_id,
            'style_description': request.style_description
        }
        
        # Get theme content from Supabase
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise HTTPException(status_code=500, detail="SUPABASE_URL and SUPABASE_KEY must be set in .env file")
            
        supabase = create_client(supabase_url, supabase_key)
        
        # Get theme content
        theme_result = supabase.table('themes').select('*').eq('id', request.theme_id).execute()
        if not theme_result.data:
            raise HTTPException(status_code=404, detail=f"Theme with ID '{request.theme_id}' not found")
        
        theme_data = theme_result.data[0]
        xml_content = theme_data.get('content')
        
        if not xml_content:
            raise HTTPException(status_code=400, detail="No XML content found in theme")
        
        # Create work directory
        work_dir = os.path.join(orchestrator.base_dir, "processing", job_id)
        os.makedirs(work_dir, exist_ok=True)
        
        # Save original XML to temporary file
        input_path = os.path.join(work_dir, f"input_{request.theme_id}.xml")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        
        # Filter the XML to keep only unique pages
        filtered_xml = orchestrator.filter_unique_pages(xml_content)
        
        # Save filtered XML
        filtered_path = os.path.join(work_dir, f"filtered_{request.theme_id}.xml")
        with open(filtered_path, "w", encoding="utf-8") as f:
            f.write(filtered_xml)
        
        # Process the filtered theme in background
        background_tasks.add_task(
            orchestrator.process_theme,
            job_id,
            filtered_path,
            request.style_description,
            skip_theme_creation=True  # Don't create new theme record since we're filtering
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
