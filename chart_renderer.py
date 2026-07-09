import json
import re
import logging
import subprocess
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

CANVAS_W = 1024
CANVAS_H = 1024
CHART_LEFT = 100
CHART_RIGHT = 960
CHART_TOP = 160
CHART_BOTTOM = 880
CHART_W = CHART_RIGHT - CHART_LEFT
CHART_H = CHART_BOTTOM - CHART_TOP
BAR_WIDTH = CHART_W / 12
BAR_GAP = BAR_WIDTH * 0.2
BAR_ACTUAL_W = BAR_WIDTH - BAR_GAP

VALUES = [
    "Life", "Freedom", "Justice", "Truth", "Security", "Prosperity",
    "Equality", "Dignity", "Peace", "Sustain", "Knowledge", "Solidarity"
]

def parse_values_json(raw: str) -> Optional[List[Tuple[float, float]]]:
    try:
        raw = re.sub(r'```json\s*', '', raw, flags=re.I)
        raw = re.sub(r'```\s*', '', raw)
        raw = raw.strip()
        
        decoder = json.JSONDecoder()
        all_arrays = []
        idx = 0
        
        while True:
            idx = raw.find('[', idx)
            if idx == -1:
                break
            
            try:
                data, end_idx = decoder.raw_decode(raw, idx)
                if isinstance(data, list) and len(data) > 0:
                    all_arrays.append((len(data), data, end_idx))
                idx = end_idx
            except json.JSONDecodeError:
                idx += 1
        
        if not all_arrays:
            logger.warning(f"[chart] No valid JSON arrays found")
            logger.warning(f"[chart] Raw input: {raw[:300]}")
            return None
        
        all_arrays.sort(key=lambda x: x[0], reverse=True)
        _, data, _ = all_arrays[0]
        
        if len(data) != 12:
            logger.warning(f"[chart] Expected 12 pairs, got {len(data)}")
            return None
        
        values = []
        for pair in data:
            if not isinstance(pair, list) or len(pair) != 2:
                values.append((0.0, 0.0))
                continue
            try:
                min_val = max(-5, min(0, float(pair[0])))
                max_val = max(0, min(5, float(pair[1])))
                values.append((min_val, max_val))
            except (ValueError, TypeError):
                values.append((0.0, 0.0))
        
        return values
    except Exception as e:
        logger.warning(f"[chart] JSON parse failed: {e}")
        logger.warning(f"[chart] Raw input: {raw[:300]}")
        return None

def get_bar_color(min_val: float, max_val: float) -> str:
    balance = (min_val + max_val) / 2
    if balance > 2:
        return "#00ff88"
    elif balance > 0.5:
        return "#88ff00"
    elif balance > -0.5:
        return "#888888"
    elif balance > -2:
        return "#ffaa00"
    else:
        return "#ff3366"

def value_to_y(v: float) -> int:
    normalized = (v + 5) / 10
    return int(CHART_BOTTOM - normalized * CHART_H)

def render_values_svg(values: List[Tuple[float, float]], title: str = "SENTIMENT ANALYSIS", subtitle: str = "") -> str:
    avg_balance = sum((min_val + max_val) / 2 for min_val, max_val in values) / len(values)
    positive_count = sum(1 for min_val, max_val in values if (min_val + max_val) / 2 > 0)
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#050810"/>
      <stop offset="100%" style="stop-color:#0a1020"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" fill="url(#bg)"/>
  <text x="512" y="64" text-anchor="middle" fill="#ffffff" font-family="Arial, sans-serif" font-size="36" font-weight="bold" letter-spacing="4">{title}</text>
  <text x="512" y="100" text-anchor="middle" fill="#8892a8" font-family="Arial, sans-serif" font-size="20" letter-spacing="2">{subtitle}</text>
  
  <g stroke="#1a2030" stroke-width="0.6">'''
    
    for i in range(11):
        y = CHART_TOP + i * (CHART_H / 10)
        svg += f'\n    <line x1="{CHART_LEFT}" y1="{y:.1f}" x2="{CHART_RIGHT}" y2="{y:.1f}"/>'
    
    svg += '\n  </g>\n  <g font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="#c8d0e0">'
    
    for i in range(11):
        val = 5 - i
        y = CHART_TOP + i * (CHART_H / 10) + 6
        svg += f'\n    <text x="80" y="{y:.1f}" text-anchor="end">{val:+d}</text>'
    
    svg += '\n  </g>'
    
    zero_y = value_to_y(0)
    svg += f'\n  <line x1="{CHART_LEFT}" y1="{zero_y}" x2="{CHART_RIGHT}" y2="{zero_y}" stroke="#ffffff" stroke-width="2" stroke-dasharray="5,5"/>'
    
    for i, (min_val, max_val) in enumerate(values):
        x = CHART_LEFT + i * BAR_WIDTH + BAR_GAP / 2
        color = get_bar_color(min_val, max_val)
        
        min_y = value_to_y(min_val)
        max_y = value_to_y(max_val)
        bar_height = abs(min_y - max_y)
        
        svg += f'\n  <rect x="{x:.1f}" y="{max_y}" width="{BAR_ACTUAL_W:.1f}" height="{bar_height}" fill="{color}" stroke="{color}" stroke-width="1" opacity="0.8"/>'
        
        balance = (min_val + max_val) / 2
        value_y = max_y - 10
        svg += f'\n  <text x="{x + BAR_ACTUAL_W/2:.1f}" y="{value_y:.1f}" text-anchor="middle" fill="{color}" font-family="Arial, sans-serif" font-size="14" font-weight="bold">{balance:+.1f}</text>'
    
    svg += '\n  <g font-family="Arial, sans-serif" font-size="14" font-weight="bold" fill="#c8d0e0">'
    for i, label in enumerate(VALUES):
        x = CHART_LEFT + i * BAR_WIDTH + BAR_WIDTH / 2
        svg += f'\n    <text x="{x:.1f}" y="{CHART_BOTTOM + 30}" text-anchor="middle">{label}</text>'
    svg += '\n  </g>'
    
    svg += f'\n  <g>'
    svg += f'\n    <circle cx="156" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="176" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">AVG: {avg_balance:+.1f}</text>'
    svg += f'\n    <circle cx="350" cy="980" r="8" fill="#88ff00"/>'
    svg += f'\n    <text x="370" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">POSITIVE: {positive_count}/12</text>'
    svg += f'\n  </g>'
    svg += '\n</svg>'
    return svg

def svg_to_png(svg_str: str, output_path: str = "chart_output.png") -> bytes:
    try:
        result = subprocess.run(
            ["rsvg-convert", "-w", "1024", "-h", "1024", "-d", "150", "-o", output_path],
            input=svg_str.encode("utf-8"),
            capture_output=True
        )
        if result.returncode != 0:
            logger.error(f"[chart] rsvg-convert failed: {result.stderr.decode()}")
            return None
        with open(output_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[chart] PNG conversion failed: {e}")
        return None

def generate_chart_image(values_json: str, title: str = "SENTIMENT ANALYSIS", subtitle: str = "") -> Optional[bytes]:
    values = parse_values_json(values_json)
    if not values:
        logger.error("[chart] Failed to parse values JSON, returning None")
        return None
    svg = render_values_svg(values, title, subtitle)
    try:
        return svg_to_png(svg)
    except Exception as e:
        logger.warning(f"[chart] PNG render failed: {e}")
        return None
