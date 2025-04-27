# WordPress Theme Transformer API Documentation

Base URL: https://vectaraaa.onrender.com

## Endpoints

### 1. Transform Theme by ID
Transform an existing WordPress theme using its ID from the database.

**Endpoint:** `/transform-by-id`  
**Method:** POST  
**Content-Type:** application/json

**Request Body:**
```json
{
    "theme_id": "your-theme-id",
    "style_description": "modern minimalist style with dark mode" // optional
}
```

**Curl Command:**
```bash
curl -X POST https://vectaraaa.onrender.com/transform-by-id \
  -H "Content-Type: application/json" \
  -d '{
    "theme_id": "fc85e373-e474-48bd-8383-503332bf0a77",
    "style_description": "modern minimalist style with dark mode"
  }'
```

### 2. Transform Theme File
Transform a WordPress theme file directly.

**Endpoint:** `/transform`  
**Method:** POST  
**Content-Type:** multipart/form-data

**Form Fields:**
- file: The WordPress theme XML file
- style_description: Description of the desired style

**Curl Command:**
```bash
curl -X POST https://vectaraaa.onrender.com/transform \
  -F "file=@path/to/your/theme.xml" \
  -F "style_description=modern professional style with clean design"
```

### 3. Generate One-Page Theme
Generate a single-page WordPress theme based on your requirements.

**Endpoint:** `/generate/onepage`  
**Method:** POST  
**Content-Type:** application/json

**Request Body:**
```json
{
    "query": "hero section with image slider, about section with team members, services section with pricing tables, contact form section",
    "style_description": "modern professional style with clean design"
}
```

**Curl Command:**
```bash
curl -X POST https://vectaraaa.onrender.com/generate/onepage \
  -H "Content-Type: application/json" \
  -d '{
    "query": "hero section with image slider, about section with team members, services section with pricing tables, contact form section",
    "style_description": "modern professional style with clean design"
  }'
```

### 4. Generate Multi-Page Theme
Generate a multi-page WordPress theme based on your requirements.

**Endpoint:** `/generate/multipage`  
**Method:** POST  
**Content-Type:** application/json

**Request Body:**
```json
{
    "query": "home page with hero section, about page with team section, services page with pricing, contact page with form",
    "style_description": "modern professional style with clean design"
}
```

**Curl Command:**
```bash
curl -X POST https://vectaraaa.onrender.com/generate/multipage \
  -H "Content-Type: application/json" \
  -d '{
    "query": "home page with hero section, about page with team section, services page with pricing, contact page with form",
    "style_description": "modern professional style with clean design"
  }'
```

### 5. Store Complete Theme
Store a complete WordPress theme with XML content.

**Endpoint:** `/store-complete-theme`  
**Method:** POST  
**Content-Type:** multipart/form-data

**Form Fields:**
- file: The WordPress theme XML file
- theme_name: Name of the theme
- style_description: (Optional) Description of the theme's style

**Curl Command:**
```bash
curl -X POST https://vectaraaa.onrender.com/store-complete-theme \
  -F "file=@path/to/your/theme.xml" \
  -F "theme_name=My Awesome Theme" \
  -F "style_description=Modern business theme with clean design"
```

### 6. Check Job Status
Check the status of a transformation or generation job.

**Endpoint:** `/status/{job_id}`  
**Method:** GET

**Curl Command:**
```bash
curl -X GET https://vectaraaa.onrender.com/status/your-job-id
```

### 7. Download Transformed Theme
Download the transformed theme file after job completion.

**Endpoint:** `/download/{job_id}`  
**Method:** GET

**Curl Command:**
```bash
curl -X GET https://vectaraaa.onrender.com/download/your-job-id --output transformed_theme.xml
```

## Response Formats

### Success Response Format
```json
{
    "job_id": "uuid-string",
    "status": "queued|processing|completed",
    "created_at": "ISO datetime string",
    "message": "Operation description"
}
```

### Error Response Format
```json
{
    "detail": "Error message description"
}
```

## Important Notes

1. All requests that initiate a transformation or generation will return a job ID immediately
2. Use the job ID to check status and download the result when complete
3. Theme transformations and generations are processed asynchronously
4. Wait for the job status to be "completed" before attempting to download
5. All dates are in ISO format
6. File uploads must be in XML format
7. The API uses JWT tokens for authentication (if enabled)

## Environment Variables Required
- SUPABASE_URL
- SUPABASE_KEY

Remember to replace placeholder values like `your-job-id` and `your-theme-id` with actual values when making requests.