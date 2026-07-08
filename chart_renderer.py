import json
import re
import logging
import subprocess
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

CANVAS_W = 1024
CANVAS_H = 1024
CHART_LEFT = 120
CHART_RIGHT = 960
CHART_TOP = 160
CHART_BOTTOM = 880
CHART_W = CHART_RIGHT - CHART_LEFT
CHART_H = CHART_BOTTOM - CHART_TOP
GRID_SIZE = 12
CELL_W = CHART_W / GRID_SIZE
CELL_H = CHART_H / GRID_SIZE

def parse_candles_json(raw: str) -> Optional[List[Dict]]:
    try:
        raw = re.sub(r'```json\s*', '', raw, flags=re.I)
        raw = re.sub(r'```\s*', '', raw)
        raw = raw.strip()
        
        match = re.search(r'\[[\s\S]*\]', raw)
        if not match:
            return None
        
        json_str = match.group(0)
        
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        if open_braces > close_braces:
            last_complete = json_str.rfind('}')
            if last_complete > 0:
                json_str = json_str[:last_complete+1]
                if not json_str.endswith(']'):
                    json_str += ']'
        
        candles = json.loads(json_str)
        
        if not isinstance(candles, list):
            return None
        
        if len(candles) < 8:
            logger.warning(f"[chart] Too few candles: {len(candles)}")
            return None
        
        if len(candles) > 12:
            candles = candles[:12]
        
        valid_candles = []
        for c in candles:
            if not isinstance(c, dict):
                continue
            if not all(k in c for k in ('o', 'h', 'l', 'c')):
                continue
            
            try:
                o = float(c['o'])
                h = float(c['h'])
                l = float(c['l'])
                c_val = float(c['c'])
            except (ValueError, TypeError):
                continue
            
            if any(v < 0 or v > 12 for v in [o, h, l, c_val]):
                o = max(0, min(12, o))
                h = max(0, min(12, h))
                l = max(0, min(12, l))
                c_val = max(0, min(12, c_val))
            
            valid_candles.append({'o': o, 'h': h, 'l': l, 'c': c_val})
        
        if len(valid_candles) < 8:
            return None
        
        return valid_candles
        
    except Exception as e:
        logger.warning(f"[chart] JSON parse failed: {e}")
        logger.warning(f"[chart] Raw input: {raw[:300]}")
        return None

def validate_and_fix_candles(candles: List[Dict]) -> List[Dict]:
    for i in range(len(candles)):
        c = candles[i]
        c['h'] = max(c['h'], c['o'], c['c'])
        c['l'] = min(c['l'], c['o'], c['c'])
        if i > 0:
            c['o'] = candles[i-1]['c']
    return candles

def value_to_y(v: float) -> int:
    return int(CHART_BOTTOM - (v / GRID_SIZE) * CHART_H)

def render_chart_svg(candles: List[Dict], title: str = "AI SENTIMENT INDEX", subtitle: str = "") -> str:
    start_val = candles[0]['o']
    peak = max(c['h'] for c in candles)
    drop = min(c['l'] for c in candles)
    now_val = candles[-1]['c']
    
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
    
    for i in range(GRID_SIZE + 1):
        x = CHART_LEFT + i * CELL_W
        svg += f'\n    <line x1="{x:.1f}" y1="{CHART_TOP}" x2="{x:.1f}" y2="{CHART_BOTTOM}"/>'
    for i in range(GRID_SIZE + 1):
        y = CHART_TOP + i * CELL_H
        svg += f'\n    <line x1="{CHART_LEFT}" y1="{y:.1f}" x2="{CHART_RIGHT}" y2="{y:.1f}"/>'
    
    svg += '\n  </g>\n  <g font-family="Arial, sans-serif" font-size="22" font-weight="bold" fill="#c8d0e0">'
    for v in [12, 9, 6, 3, 0]:
        y = value_to_y(v) + 8
        svg += f'\n    <text x="104" y="{y}" text-anchor="end">{v}</text>'
    svg += '\n  </g>\n  <g font-family="Arial, sans-serif" font-size="22" font-weight="bold" fill="#c8d0e0">'
    for i in range(1, 13):
        x = CHART_LEFT + (i - 0.5) * CELL_W
        svg += f'\n    <text x="{x:.1f}" y="{CHART_BOTTOM + 36}" text-anchor="middle">{i}</text>'
    svg += '\n  </g>'
    
    for i, c in enumerate(candles):
        cx = CHART_LEFT + (i + 0.5) * CELL_W
        is_bull = c['c'] >= c['o']
        color = "#00ff88" if is_bull else "#ff3366"
        body_top = value_to_y(max(c['o'], c['c']))
        body_bot = value_to_y(min(c['o'], c['c']))
        body_h = max(body_bot - body_top, 4)
        wick_top = value_to_y(c['h'])
        wick_bot = value_to_y(c['l'])
        bar_w = CELL_W * 0.6
        x1 = cx - bar_w / 2
        
        svg += f'\n  <g>'
        svg += f'\n    <line x1="{cx:.1f}" y1="{wick_top}" x2="{cx:.1f}" y2="{wick_bot}" stroke="{color}" stroke-width="4"/>'
        svg += f'\n    <rect x="{x1:.1f}" y="{body_top}" width="{bar_w:.1f}" height="{body_h}" fill="{color}" stroke="{color}" stroke-width="1"/>'
        svg += f'\n  </g>'
    
    svg += f'\n  <g>'
    svg += f'\n    <rect x="70" y="960" width="20" height="20" fill="#00ff88"/>'
    svg += f'\n    <text x="100" y="978" fill="#00ff88" font-family="Arial, sans-serif" font-size="22" font-weight="bold">BULLISH</text>'
    svg += f'\n    <rect x="800" y="960" width="20" height="20" fill="#ff3366"/>'
    svg += f'\n    <text x="830" y="978" fill="#ff3366" font-family="Arial, sans-serif" font-size="22" font-weight="bold">BEARISH</text>'
    svg += f'\n  </g>'
    svg += f'\n  <g>'
    svg += f'\n    <circle cx="220" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="240" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">START: {start_val:.1f}</text>'
    svg += f'\n    <circle cx="400" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="420" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">PEAK: {peak:.1f}</text>'
    svg += f'\n    <circle cx="570" cy="980" r="8" fill="#ff3366"/>'
    svg += f'\n    <text x="590" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">DROP: {drop:.1f}</text>'
    svg += f'\n    <circle cx="730" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="750" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">NOW: {now_val:.1f}</text>'
    svg += f'\n  </g>'
    svg += '\n</svg>'
    
    return svg

def svg_to_png(svg_str: str, output_path: str = "chart_output.png") -> bytes:
    try:
        result = subprocess.run(
            ["rsvg-convert", "-w", "1024", "-h", "1024", "-o", output_path],
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

def generate_default_candles() -> List[Dict]:
    return [
        {"o": 6.0, "h": 6.5, "l": 5.5, "c": 6.2},
        {"o": 6.2, "h": 7.0, "l": 6.0, "c": 6.8},
        {"o": 6.8, "h": 7.5, "l": 6.5, "c": 7.2},
        {"o": 7.2, "h": 8.0, "l": 7.0, "c": 7.8},
        {"o": 7.8, "h": 8.5, "l": 7.5, "c": 8.2},
        {"o": 8.2, "h": 9.0, "l": 8.0, "c": 8.8},
        {"o": 8.8, "h": 9.5, "l": 8.5, "c": 9.2},
        {"o": 9.2, "h": 9.8, "l": 8.8, "c": 9.0},
        {"o": 9.0, "h": 9.5, "l": 8.5, "c": 8.7},
        {"o": 8.7, "h": 9.0, "l": 8.2, "c": 8.5},
        {"o": 8.5, "h": 8.8, "l": 8.0, "c": 8.3},
        {"o": 8.3, "h": 8.6, "l": 7.8, "c": 8.0}
    ]

def generate_chart_image(candles_json: str, title: str = "AI SENTIMENT INDEX", subtitle: str = "") -> Optional[bytes]:
    candles = parse_candles_json(candles_json)
    
    if not candles:
        logger.warning("[chart] Using default candles pattern")
        candles = generate_default_candles()
    
    candles = validate_and_fix_candles(candles)
    svg = render_chart_svg(candles, title, subtitle)
    
    try:
        return svg_to_png(svg)
    except Exception as e:
        logger.warning(f"[chart] PNG render failed: {e}")
        return None
