import os
import json
import logging
import chart_renderer

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    title = os.environ.get("TITLE", "AI SENTIMENT INDEX")
    subtitle = os.environ.get("SUBTITLE", "TEST")
    candles_json = os.environ.get("CANDLES_JSON", "[]")
    
    logger.info(f"[TEST] Title: {title}")
    logger.info(f"[TEST] Subtitle: {subtitle}")
    logger.info(f"[TEST] Candles JSON: {candles_json[:200]}")
    
    candles = chart_renderer.parse_candles_json(candles_json)
    if not candles:
        logger.error("[TEST] Failed to parse candles JSON")
        return
    
    logger.info(f"[TEST] Parsed {len(candles)} candles")
    for i, c in enumerate(candles):
        logger.info(f"[TEST] Candle {i+1}: O={c['o']:.1f} H={c['h']:.1f} L={c['l']:.1f} C={c['c']:.1f}")
    
    candles = chart_renderer.validate_and_fix_candles(candles)
    
    svg = chart_renderer.render_chart_svg(candles, title, subtitle)
    
    with open("chart_output.svg", "w") as f:
        f.write(svg)
    logger.info("[TEST] SVG saved to chart_output.svg")
    
    png_bytes = chart_renderer.svg_to_png(svg)
    if png_bytes:
        with open("chart_output.png", "wb") as f:
            f.write(png_bytes)
        logger.info(f"[TEST] PNG saved to chart_output.png ({len(png_bytes)} bytes)")
    else:
        logger.error("[TEST] PNG conversion failed")

if __name__ == "__main__":
    main()
