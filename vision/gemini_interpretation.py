import os
from dotenv import load_dotenv
import google.genai as genai
import cv2
import base64
from io import BytesIO
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# Initialize Gemini 2.5 client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def frame_to_base64(frame):
    """Convert OpenCV frame to base64 string for Gemini"""
    # Convert BGR to RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Convert to PIL Image
    pil_image = Image.fromarray(rgb_frame)
    
    # Convert to base64
    buffer = BytesIO()
    pil_image.save(buffer, format="JPEG", quality=85)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return img_base64

def interpret_scene(frame, detections):
    """Send frame image and detections to Gemini 2.5 for scene interpretation"""
    if not detections:
        return "No objects detected in the scene."
    
    try:
        # Convert frame to base64
        img_base64 = frame_to_base64(frame)
        
        # Create detection summary for context
        detection_info = f"YOLO detected {len(detections)} objects with bounding boxes:"
        for i, d in enumerate(detections):
            x1, y1, x2, y2 = d["bbox"]
            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            detection_info += f"\nObject {i+1}: center at ({center_x}, {center_y}), confidence: {d['confidence']:.2f}"
        
        # Create the prompt
        prompt = f"""
{detection_info}

Looking at this image, identify what objects you see and respond in exactly this format:

Objects detected:
[object name] at ([x], [y]) - confidence: [confidence]
[object name] at ([x], [y]) - confidence: [confidence]

1. [Brief scene description]
2. [Small 2 line description of each object]

Be concise. Do not include safety concerns, recommendations, or additional advice.
"""

        # Send image and prompt to Gemini
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_base64
                            }
                        }
                    ]
                }
            ]
        )
        
        return response.text
        
    except Exception as e:
        return f"Error interpreting scene: {str(e)}"