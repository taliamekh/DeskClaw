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

def image_to_base64(image_bgr):
    """Convert OpenCV BGR image to base64 JPEG for Gemini."""
    # Convert BGR to RGB
    rgb_frame = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    
    # Convert to PIL Image
    pil_image = Image.fromarray(rgb_frame)
    
    # Convert to base64
    buffer = BytesIO()
    pil_image.save(buffer, format="JPEG", quality=85)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return img_base64

def interpret_scene(crop_payloads):
    """Send only in-grid detection crops and metadata to Gemini 2.5."""
    if not crop_payloads:
        return "No in-grid objects detected in the scene."
    
    try:
        # Create detection summary for context.
        detection_info = f"YOLO provided {len(crop_payloads)} cropped object images (in-grid only):"
        parts = []
        for i, d in enumerate(crop_payloads):
            x1, y1, x2, y2 = d["bbox"]
            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            yolo_label = str(d.get("label", "object"))
            grid_info = ""
            if d.get("grid_position"):
                gx = d["grid_position"]["x"]
                gy = d["grid_position"]["y"]
                grid_info = f", grid: ({gx:.2f}, {gy:.2f})"
            world_info = ""
            if d.get("position_cm"):
                wx = d["position_cm"]["x"]
                wy = d["position_cm"]["y"]
                world_info = f", world_cm: ({wx:.1f}, {wy:.1f})"
            detection_info += (
                f"\nObject {i+1}: yolo_label={yolo_label}, center at ({center_x}, {center_y})"
                f"{grid_info}{world_info}, "
                f"confidence: {d['confidence']:.2f}"
            )

            crop_base64 = image_to_base64(d["image"])
            parts.append({"text": f"Object crop {i+1}"})
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": crop_base64,
                    }
                }
            )
        
        # Create the prompt
        prompt = f"""
{detection_info}

Looking at the provided object crops (not the full scene), identify each object and respond in exactly this format:

Detected: [YOLO label exactly as provided] at pixel([x], [y]) grid([gx], [gy]) world_cm([wx], [wy]) - confidence: [confidence]
Description: [one concise sentence about this object]

Rules:
- Return one Detected/Description pair per object crop.
- For each object, the Detected name must exactly match its provided yolo_label.
- Keep each Description to one sentence.
- Do not include numbered lists, scene summary, recommendations, or extra text.
"""

        # Send image and prompt to Gemini
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents={"parts": [{"text": prompt}] + parts},
        )
        
        return response.text
        
    except Exception as e:
        return f"Error interpreting scene: {str(e)}"