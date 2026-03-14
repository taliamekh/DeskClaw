import google.generativeai as genai

genai.configure(api_key="YOUR_API_KEY")

model = genai.GenerativeModel("gemini-1.5-flash")

def build_prompt(detections):

    objects = "\n".join(
        [f"{d['label']} confidence:{d['confidence']:.2f}" for d in detections]
    )

    return f"""
Objects detected from a bird's-eye camera:

{objects}

Explain the scene and determine which object would be easiest
for a robotic claw to pick up first.
"""

def interpret_scene(detections):

    prompt = build_prompt(detections)

    response = model.generate_content(prompt)

    return response.text