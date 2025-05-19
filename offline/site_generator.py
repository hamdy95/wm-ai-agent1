import argparse
import os
import sys
import time
from typing import Optional
import uuid

# Import our agents
from onepage_agent import OnePageSiteGenerator
from multipage_agent import MultiPageSiteGenerator

def generate_one_page_site(query: str, output_file: Optional[str] = None, style_description: Optional[str] = None) -> str:
    """Generate a one-page site based on user query"""
    print("Starting one-page site generation process...")
    
    # Setup agent
    generator = OnePageSiteGenerator()
    
    # Set default output file if not provided
    if not output_file:
        output_file = os.path.join(os.getcwd(), "output", f"onepage_site_{uuid.uuid4()}.xml")
    
    # Make sure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    try:
        # Generate one-page site
        print(f"Analyzing query: '{query}'")
        start_time = time.time()
        
        # Generate the site
        generated_path = generator.create_one_page_site(query, output_file, style_description)
        
        generation_time = time.time() - start_time
        print(f"  ✓ Site generation completed in {generation_time:.2f} seconds")
        print(f"  ✓ Output saved to: {generated_path}")
        
        return generated_path
        
    except Exception as e:
        print(f"\nError during site generation: {e}")
        sys.exit(1)

def generate_multi_page_site(query: str, output_file: Optional[str] = None, style_description: Optional[str] = None) -> str:
    """Generate a multi-page site based on user query"""
    print("Starting multi-page site generation process...")
    
    # Setup agent
    generator = MultiPageSiteGenerator()
    
    # Set default output file if not provided
    if not output_file:
        output_file = os.path.join(os.getcwd(), "output", f"multipage_site_{uuid.uuid4()}.xml")
    
    # Make sure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    try:
        # Generate multi-page site
        print(f"Analyzing query: '{query}'")
        start_time = time.time()
        
        # Generate the site
        generated_path = generator.create_multi_page_site(query, output_file)
        
        generation_time = time.time() - start_time
        print(f"  ✓ Site generation completed in {generation_time:.2f} seconds")
        print(f"  ✓ Output saved to: {generated_path}")
        
        return generated_path
        
    except Exception as e:
        print(f"\nError during site generation: {e}")
        sys.exit(1)

def print_help():
    """Print help information"""
    print("WordPress Site Generator")
    print("=======================")
    print("Generate one-page or multi-page WordPress sites from text queries")
    print("\nUsage:")
    print("  python site_generator.py onepage \"I need a site with hero, about and contact sections\"")
    print("  python site_generator.py multipage \"I need a site with 5 pages: home, about, services, portfolio, contact\"")
    print("\nOptions:")
    print("  --output, -o   Specify output file path")
    print("  --help, -h     Show this help message")

def main():
    parser = argparse.ArgumentParser(description='Generate WordPress Sites')
    parser.add_argument('site_type', choices=['onepage', 'multipage'], help='Type of site to generate')
    parser.add_argument('query', type=str, help='Description of the site you want to generate')
    parser.add_argument('--output', '-o', type=str, help='Path to save the generated XML file')
    parser.add_argument('--style', '-s', type=str, help='Style description for the site')
    
    if len(sys.argv) == 1 or sys.argv[1] in ['--help', '-h']:
        print_help()
        sys.exit(0)
        
    args = parser.parse_args()
    
    # Generate site based on type
    if args.site_type == 'onepage':
        output_path = generate_one_page_site(args.query, args.output, args.style)
    else:
        output_path = generate_multi_page_site(args.query, args.output, args.style)
    
    print("\nSite generation completed successfully!")
    print("You can now import this XML file into WordPress.")

if __name__ == "__main__":
    main()
