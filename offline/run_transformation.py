import argparse
import os
import sys
import time
from typing import Optional
import uuid

# Import our agents
from agentoff import FixedElementorExtractor
from transformation import ContentTransformationAgent
from replace_agent import OfflineReplaceAgent

def validate_file(file_path: str, file_type: str = 'xml') -> bool:
    """Validate that file exists and has the correct extension"""
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist")
        return False
        
    if not file_path.lower().endswith(f'.{file_type}'):
        print(f"Error: File {file_path} is not a {file_type} file")
        return False
        
    return True

def run_transformation(input_file: str, style_description: str, output_file: Optional[str] = None) -> str:
    """Run the complete transformation process"""
    print("Starting WordPress theme transformation process...")
    
    # Setup agents
    extractor = FixedElementorExtractor()
    transformer = ContentTransformationAgent()
    replacer = OfflineReplaceAgent()
    
    # Set default output file if not provided
    if not output_file:
        input_dir, input_filename = os.path.split(input_file)
        filename_base, _ = os.path.splitext(input_filename)
        output_file = os.path.join(input_dir, f"{filename_base}_transformed.xml")
    
    # Make sure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    # Generate temporary directory
    process_id = str(uuid.uuid4())
    working_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing", process_id)
    os.makedirs(working_dir, exist_ok=True)
    
    try:
        # Step 1: Extract content
        print("Step 1/3: Extracting content from WordPress theme...")
        start_time = time.time()
        theme_id, pages_data, sections_data = extractor.process_theme(input_file)
        extraction_time = time.time() - start_time
        print(f"  ✓ Extraction completed in {extraction_time:.2f} seconds")
        print(f"  ✓ Found {len(pages_data)} pages and {len(sections_data)} sections")
        
        # Step 2: Transform content
        print(f"Step 2/3: Transforming content using style description: '{style_description}'")
        start_time = time.time()
        transformation_result = transformer.transform_theme_content(theme_id, style_description)
        transformation_time = time.time() - start_time
        
        # Save transformation result for debugging
        transformed_path = os.path.join(working_dir, f"transformed_{theme_id}.json")
        with open(transformed_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(transformation_result, f, ensure_ascii=False, indent=2)
            
        print(f"  ✓ Transformation completed in {transformation_time:.2f} seconds")
        print(f"  ✓ Transformed {len(transformation_result['text_transformations'])} texts")
        print(f"  ✓ Generated {len(transformation_result['color_palette']['new_colors'])} colors")
        
        # Step 3: Replace content in original theme
        print("Step 3/3: Generating new theme with transformed content...")
        start_time = time.time()
        replacer.replace_text_and_colors(input_file, transformed_path, output_file)
        replacement_time = time.time() - start_time
        print(f"  ✓ Theme generation completed in {replacement_time:.2f} seconds")
        
        total_time = extraction_time + transformation_time + replacement_time
        print(f"\nTransformation process completed successfully in {total_time:.2f} seconds!")
        print(f"New theme saved to: {output_file}")
        
        return output_file
        
    except Exception as e:
        print(f"\nError during transformation process: {e}")
        sys.exit(1)
    finally:
        # Clean up working directory
        import shutil
        if os.path.exists(working_dir):
            shutil.rmtree(working_dir)

def main():
    parser = argparse.ArgumentParser(description='Transform WordPress Elementor Theme')
    parser.add_argument('input_file', type=str, help='Path to the WordPress XML export file')
    parser.add_argument('style_description', type=str, help='Description of the desired style')
    parser.add_argument('--output', '-o', type=str, help='Path to save the transformed XML file')
    
    args = parser.parse_args()
    
    # Validate input file
    if not validate_file(args.input_file, 'xml'):
        sys.exit(1)
    
    # Run transformation
    output_file = run_transformation(args.input_file, args.style_description, args.output)
    
    print("\nYou can now import the transformed theme into WordPress!")

if __name__ == "__main__":
    main() 