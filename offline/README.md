# WordPress Theme Transformer & Generator (Offline)

A comprehensive offline toolset for WordPress theme transformation and generation using AI. This system allows extraction, transformation, and replacement of content and styling, as well as generation of new themes from scratch.

## Overview

This system consists of five main agents:

1. **Extract Agent** (`agentoff.py`) - Extracts texts, colors, and content from WordPress Elementor XML exports and stores them in Supabase.
2. **Transform Agent** (`transformation.py`) - Transforms the extracted texts and colors based on a style description.
3. **Replace Agent** (`replace_agent.py`) - Replaces the original content with the transformed content in the theme.
4. **One-Page Site Generator** (`onepage_agent.py`) - Creates a single-page WordPress site by intelligently selecting sections.
5. **Multi-Page Site Generator** (`multipage_agent.py`) - Creates a multi-page WordPress site by selecting and organizing pages.

Plus additional components:

- **Orchestra Agent** (`orchestra_agent.py`) - FastAPI application that orchestrates the workflow.
- **CLI Runners** - Command-line tools for running transformations and generating sites:
  - `run_transformation.py` - For transforming existing themes
  - `site_generator.py` - For generating new themes from scratch

## Installation

### Prerequisites

- Python 3.8+
- Required packages (install via `pip`):
  - fastapi
  - uvicorn
  - openai
  - supabase
  - python-dotenv
  - python-multipart (for FastAPI file uploads)

### Setup

1. Clone this repository:

```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install required packages:

```bash
pip install -r requirements.txt
```

3. Set up environment variables in the `.env` file:

```
OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### Directory Structure

```
offline/
├── agentoff.py           # Extraction agent
├── transformation.py     # Transformation agent
├── replace_agent.py      # Replacement agent
├── onepage_agent.py      # One-page site generator
├── multipage_agent.py    # Multi-page site generator
├── orchestra_agent.py    # API orchestrator
├── run_transformation.py # CLI for transformations
├── site_generator.py     # CLI for site generation
├── requirements.txt      # Project dependencies
└── README.md             # This documentation

input/                    # Directory for input XML files
output/                   # Directory for output XML files
processing/               # Temporary processing directory
```

## Usage

You can use the system in the following ways:

### 1. Command Line Interface (CLI) for Theme Transformation

Transform an existing WordPress theme:

```bash
python run_transformation.py input_file.xml "style description" --output output_file.xml
```

**Arguments:**
- `input_file.xml`: Path to WordPress XML export file
- `"style description"`: Text description of the desired style (e.g., "modern corporate design with blue tones")
- `--output output_file.xml`: (Optional) Path for the transformed output file

### 2. Command Line Interface (CLI) for Site Generation

Generate a one-page or multi-page WordPress site from scratch:

```bash
# Generate a one-page site
python site_generator.py onepage "I need a website with hero section, about us, services, and contact form"

# Generate a multi-page site
python site_generator.py multipage "I need a site with 5 pages: home, about, services, portfolio, contact"
```

**Arguments:**
- `onepage` or `multipage`: Type of site to generate
- `"query"`: Description of what you want in the site
- `--output file.xml`: (Optional) Path for the output file
- `--style "description"`: (Optional) Style description for visual design

### 3. REST API

Start the API server:

```bash
cd offline
python orchestra_agent.py
```

The API will be available at `http://localhost:8000` with the following endpoints:

#### Transformation Endpoints

| Endpoint | Method | Description | Parameters |
|----------|--------|-------------|------------|
| `/transform` | POST | Transform a WordPress theme using file upload | `theme_file`: XML file upload<br>`style_description`: Text description of style |
| `/transform-json` | POST | Alternative upload with JSON style | `theme_file`: XML file upload<br>`style`: JSON object with description field |
| `/transform-by-id` | POST | Transform a theme by its ID | JSON body with:<br>`theme_id`: UUID of theme in database<br>`style_description`: Text description of style |

#### Generation Endpoints

| Endpoint | Method | Description | Parameters |
|----------|--------|-------------|------------|
| `/generate/onepage` | POST | Generate a one-page site | JSON body with:<br>`query`: Description of sections needed<br>`style_description`: (Optional) Text description of style |
| `/generate/multipage` | POST | Generate a multi-page site | JSON body with:<br>`query`: Description of pages needed<br>`style_description`: (Optional) Text description of style |

#### Status and Download Endpoints

| Endpoint | Method | Description | Parameters |
|----------|--------|-------------|------------|
| `/status/{job_id}` | GET | Check job status | `job_id`: UUID of the job |
| `/download/{job_id}` | GET | Download the result | `job_id`: UUID of the job |

#### Example API Usage

```bash
# Transform theme with file upload
curl -X POST http://localhost:8000/transform \
  -F "theme_file=@path_to_theme.xml" \
  -F "style_description=modern design with blue tones"

# Transform theme by ID
curl -X POST http://localhost:8000/transform-by-id \
  -H "Content-Type: application/json" \
  -d '{"theme_id": "c506a002-029a-4ce3-b0bc-3eefdd331c7a", "style_description": "modern design with blue tones"}'

# Generate one-page site
curl -X POST http://localhost:8000/generate/onepage \
  -H "Content-Type: application/json" \
  -d '{"query": "I need a business website with hero, about, services, and contact sections", "style_description": "modern corporate style with blue tones"}'

# Check status
curl -X GET http://localhost:8000/status/job_id_from_previous_response

# Download result
curl -X GET http://localhost:8000/download/job_id_from_previous_response -o result.xml
```

## How It Works

### Database Structure

The system relies on a Supabase database with the following tables:

| Table | Description | Key Fields |
|-------|-------------|------------|
| `themes` | Stores theme metadata | `id`, `title`, `metadata` |
| `pages` | Stores pages extracted from themes | `id`, `theme_id`, `title`, `category`, `elementor_data` |
| `sections` | Stores sections extracted from pages | `id`, `theme_id`, `page_id`, `category`, `content` |
| `transformation_data` | Stores extracted text and colors | `id`, `theme_id`, `texts`, `colors` |

### Theme Transformation

1. **Extraction Phase**:
   - Parses the WordPress XML export
   - Identifies pages, sections, text content, and colors
   - Stores data in Supabase for processing

2. **Transformation Phase**:
   - Uses OpenAI to generate new text content based on style description
   - Creates a new color palette that matches the style description
   - Preserves structure and formats while changing content

3. **Replacement Phase**:
   - Takes the transformed content and colors
   - Replaces them in the original theme structure
   - Preserves white backgrounds and structural elements
   - Generates a new XML file that can be imported into WordPress

### Site Generation

1. **One-Page Site Generation**:
   - Analyzes the user query to identify required sections (hero, about, etc.)
   - Searches the Supabase database for appropriate sections
   - Randomly selects one section of each type
   - Combines the sections in a logical order
   - Creates a WordPress XML file with the selected sections

2. **Multi-Page Site Generation**:
   - Analyzes the user query to identify required pages (home, about, etc.)
   - Searches the Supabase database for pages of each type
   - Creates a WordPress XML file with the selected pages
   - Generates navigation menu items to connect the pages

## Technical Details

### Agent Capabilities

| Agent | Main Functions | Input | Output |
|-------|---------------|-------|--------|
| Extract Agent | `process_theme()` | WordPress XML file | Theme ID, extracted text/colors |
| Transform Agent | `transform_theme_content()` | Theme ID, style description | Transformed text/colors |
| Replace Agent | `replace_text_and_colors()` | XML file, transformed content | New XML file |
| One-Page Generator | `create_one_page_site()` | User query | WordPress XML file |
| Multi-Page Generator | `create_multi_page_site()` | User query | WordPress XML file |

### API Response Format

All API endpoints return a response with a job ID that can be used to check status and download results:

```json
{
  "job_id": "98a1b4b3-f947-46c1-b981-c542429efbc6",
  "status": "queued",
  "created_at": "2023-04-10T15:32:10.123456"
}
```

Job status endpoint returns more detailed information:

```json
{
  "job_id": "98a1b4b3-f947-46c1-b981-c542429efbc6",
  "status": "completed",
  "created_at": "2023-04-10T15:32:10.123456",
  "completed_at": "2023-04-10T15:35:22.654321",
  "output_url": "/download/98a1b4b3-f947-46c1-b981-c542429efbc6",
  "job_type": "multi_page_site"
}
```

## Notes

- This offline version stores data in Supabase but processes everything locally.
- The transformation uses OpenAI's API, so an internet connection is still required for that step.
- White backgrounds are preserved by default to maintain readability.
- Generated sites require styling using the transformation process for a cohesive look.

## Troubleshooting

- **Error connecting to Supabase**: Check your `.env` file and ensure proper credentials.
- **OpenAI API errors**: Verify your API key and check OpenAI service status.
- **File not found errors**: Ensure input XML paths are correct.
- **Invalid XML errors**: The input file must be a valid WordPress export file.
- **Empty sections/pages**: The database may not have the requested content types.
- **XML parsing errors**: If you encounter "duplicate attribute" errors, this is typically caused by issues in the XML generation process. The system has been updated to fix these issues.

## License

[Your License Information] 