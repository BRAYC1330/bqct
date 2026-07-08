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
        
        first_array = re.search(r'\[[^\[\]]*\]', raw)
        if not first_array:
            return None
        json_str = first_array.group(0)
        
        data = json.loads(json_str)
        if not isinstance(data, list):
            return None
        if len(data) < 8:
            logger.warning(f"[chart] Too few items: {len(data)}")
            return None
        if len(data) > 12:
            data = data[:12]
        if isinstance(data[0], dict):
            valid_candles = []
            for c in data:
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
        elif isinstance(data[0], (int, float)):
            candles = []
            prev_close = 6.0
            for val in data:
                try:
                    close_val = float(val)
                    if close_val < 0 or close_val > 12:
                        close_val = max(0, min(12, close_val))
                    open_val = prev_close
                    high_val = max(open_val, close_val) + 0.5
                    low_val = min(open_val, close_val) - 0.5
                    high_val = max(0, min(12, high_val))
                    low_val = max(0, min(12, low_val))
                    candles.append({'o': open_val, 'h': high_val, 'l': low_val, 'c': close_val})
                    prev_close = close_val
                except (ValueError, TypeError):
                    continue
            if len(candles) < 8:
                return None
            return candles
        else:
            return None
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
    svg += f'\n    <circle cx="156" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="176" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">START: {start_val:.1f}</text>'
    svg += f'\n    <circle cx="350" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="370" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">PEAK: {peak:.1f}</text>'
    svg += f'\n    <circle cx="540" cy="980" r="8" fill="#ff3366"/>'
    svg += f'\n    <text x="560" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">DROP: {drop:.1f}</text>'
    svg += f'\n    <circle cx="730" cy="980" r="8" fill="#00ff88"/>'
    svg += f'\n    <text x="750" y="988" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="20" font-weight="bold">NOW: {now_val:.1f}</text>'
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

def generate_chart_image(candles_json: str, title: str = "AI SENTIMENT INDEX", subtitle: str = "") -> Optional[bytes]:
    candles = parse_candles_json(candles_json)
    if not candles:
        logger.error("[chart] Failed to parse candles JSON, returning None")
        return None
    candles = validate_and_fix_candles(candles)
    svg = render_chart_svg(candles, title, subtitle)
    try:
        return svg_to_png(svg)
    except Exception as e:
        logger.warning(f"[chart] PNG render failed: {e}")
        return None
