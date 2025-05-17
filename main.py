from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import os
from openai import OpenAI
from typing import Optional, Dict, Any
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Document Extraction API",
    description="API for extracting structured data from documents using AI vision models",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen-vl-max")

# Pydantic models
class DocumentRequest(BaseModel):
    image_url: HttpUrl
    model: Optional[str] = DEFAULT_MODEL

class DocumentResponse(BaseModel):
    name: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    total_amount: Optional[float] = None
    item: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None

@app.post("/extract", response_model=DocumentResponse)
async def extract_document_data(request: DocumentRequest):
    """
    Extract structured data from a document image
    
    - Accepts an image URL
    - Returns structured information including merchant, date, amount and more
    """
    try:
        # Set up OpenAI client
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=BASE_URL,
        )
        
        # Define the extraction prompt
        prompt_text = """
        You are a smart invoice parser. Given the following receipt or invoice image, extract these fields and return the result in JSON format:
        
        - name
        - date_of_transaction (format: YYYYMMDD)
        - description
        - item (description of item in receipt in sentences)
        - total_amount
        
        If any field is missing, return null.
        """
        
        # Create completion request
        logger.info(f"Processing document from URL: {request.image_url}")
        completion = client.chat.completions.create(
            model=request.model,
            messages=[
                {
                    "role": "system",
                    "content": [{"type": "text", "text": prompt_text}]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": str(request.image_url)
                            }
                        }
                    ]
                }
            ]
        )
        
        # Get the JSON response from the model
        response_content = completion.choices[0].message.content
        logger.info(f"Raw response: {response_content}")
        
        # Try to parse the JSON response
        import json
        import re
        
        # If the response is wrapped in markdown code blocks, extract the JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_content)
        if json_match:
            extracted_json = json_match.group(1)
        else:
            # Otherwise try to find anything that looks like a JSON object
            json_match = re.search(r'({[\s\S]*})', response_content)
            extracted_json = json_match.group(1) if json_match else response_content
        
        try:
            extracted_data = json.loads(extracted_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {extracted_json}")
            # If JSON parsing fails, return the raw response
            return DocumentResponse(
                raw_response={"text": response_content}
            )
        
        # Construct response with extracted data
        return DocumentResponse(
            name=extracted_data.get("name"),
            date=extracted_data.get("date_of_transaction"),
            description=extracted_data.get("description"),
            item=extracted_data.get("item"),
            total_amount=extracted_data.get("total_amount"),
            raw_response=extracted_data
        )
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)