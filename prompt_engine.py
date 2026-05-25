import random
import logging
logger = logging.getLogger(__name__)

STYLES = ["oil painting", "watercolor", "pencil sketch", "graffiti art", "pixel art", "ukiyo-e print", "cave painting style", "pop art", "charcoal drawing", "collage"]
COLORS = ["monochrome with red accents", "black and white", "pastel tones", "gold and black luxury", "earthy tones", "vibrant rainbow", "sepia", "duotone blue and orange"]
SETTINGS = [
    "a futuristic digital marketplace", "a high-tech bank vault", "an ancient library of glowing glass books",
    "a chaotic abstract space with geometric shards", "a lush digital garden growing circuit boards",
    "a dark control room monitoring global networks", "a minimalist white void", "a neon-lit server farm",
    "a floating sky-city above clouds", "an underground bunker filled with screens"
]
CRYPTO_OBJECTS = [
    "giant floating golden coins", "holographic trading charts", "streams of flowing data blocks",
    "a massive digital ledger", "glowing transaction nodes", "a vault door made of code",
    "floating tokens spinning in mid-air", "a scale balancing digital assets", "a growing crystal representing growth"
]
ROBOT_ACTIONS = [
    "inspecting a glowing map closely", "typing rapidly on a holographic interface",
    "carrying a heavy chest of digital assets", "observing a rising graph with focus",
    "standing triumphantly atop a data structure", "juggling luminous tokens",
    "connecting cables to a pulsing mainframe", "analyzing floating symbols", "navigating through floating barriers"
]
ATMOSPHERE = ["cinematic lighting", "dramatic shadows", "volumetric fog", "clean minimalist lines", "dynamic motion blur", "sharp high-contrast focus", "soft dreamy haze", "neon reflections"]
PERSPECTIVES = ["wide angle shot", "low angle hero shot", "isometric view", "close-up portrait", "bird's eye view", "symmetrical composition", "diagonal dynamic perspective", "over-the-shoulder shot"]

ROBOT_DESC = "a small white and gray matte robot with a round head and expressive lens-eyes, solid mechanical joints, fully assembled, no extra limbs"

def build_image_prompt(keyword: str) -> tuple[str, str]:
    style = random.choice(STYLES)
    color = random.choice(COLORS)
    setting = random.choice(SETTINGS)
    obj = random.choice(CRYPTO_OBJECTS)
    action = random.choice(ROBOT_ACTIONS)
    atmos = random.choice(ATMOSPHERE)
    persp = random.choice(PERSPECTIVES)

    prompt = (
        f"{style} style, {color} palette. {setting} filled with {obj}, representing '{keyword}'. "
        f"In the center, {ROBOT_DESC} is {action}. "
        f"{atmos}, {persp}, highly detailed, masterpiece."
    )
    negative = (
        "text, watermark, signature, blurry, low quality, extra limbs, multiple arms, missing legs, "
        "deformed, mutation, ugly, disfigured, floating body parts, disconnected limbs, "
        "neon glow, cyan highlights, green tints, cyberpunk lighting, realistic photo"
    )
    logger.info(f"[prompt_engine] Scene: {style} | {setting} | {action} | {keyword}")
    return prompt, negative
