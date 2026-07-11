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
    "Equality", "Dignity", "Entertain", "Sustain", "Knowledge", "Solidarity"
]

VALUE_ABBR = {
    "Life": "LI", "Freedom": "FR", "Justice": "JU", "Truth": "TR",
    "Security": "SE", "Prosperity": "PR", "Equality": "EQ", "Dignity": "DI",
    "Entertain": "EN", "Sustain": "SU", "Knowledge": "KN", "Solidarity": "SO"
}

def parse_bracket_format(raw: str) -> Optional[List[Tuple[float, float]]]:
    values = []
    clean = raw.replace('**', '').replace('*', '')
    pattern = r'\[\s*([-\d.]+)\s*,\s*\+?([-\d.]+)\s*\]'
    matches = re.findall(pattern, clean)
    if len(matches) < 12:
        logger.warning(f"[chart] Expected at least 12 pairs, got {len(matches)}")
        return None
    last_12 = matches[-12:]
    for neg_str, pos_str in last_12:
        try:
            neg = max(-5, min(0, float(neg_str)))
            pos = max(0, min(5, float(pos_str)))
            values.append((neg, pos))
        except ValueError:
            values.append((0.0, 0.0))
    return values

def parse_text_format(raw: str) -> Optional[List[Tuple[float, float]]]:
    values = []
    clean = raw.replace('**', '').replace('*', '')
    neg_pattern = r'Negative:\s*([-\d.]+)'
    pos_pattern = r'Positive:\s*\+?([-\d.]+)'
    neg_matches = re.findall(neg_pattern, clean)
    pos_matches = re.findall(pos_pattern, clean)
    if len(neg_matches) < 12 or len(pos_matches) < 12:
        logger.warning(f"[chart] Expected 12 pairs, got {len(neg_matches)} neg, {len(pos_matches)} pos")
        return None
    last_12_neg = neg_matches[-12:]
    last_12_pos = pos_matches[-12:]
    for i in range(12):
        try:
            neg = max(-5, min(0, float(last_12_neg[i])))
            pos = max(0, min(5, float(last_12_pos[i])))
            values.append((neg, pos))
        except ValueError:
            values.append((0.0, 0.0))
    return values

def parse_inline_scores(raw: str) -> Optional[List[Tuple[float, float]]]:
    values = []
    clean = raw.replace('**', '').replace('*', '')
    sections = re.split(r'\n\d+\.\s+', clean)
    if len(sections) < 13:
        logger.warning(f"[chart] Expected 12 sections, got {len(sections)}")
        return None
    for i, section in enumerate(sections[1:13], 1):
        scores = re.findall(r'[+-]\d+', section)
        if len(scores) >= 1:
            score = int(scores[-1])
            if score > 0:
                values.append((0.0, min(5, float(score))))
            else:
                values.append((max(-5, float(score)), 0.0))
        else:
            values.append((0.0, 0.0))
    if all(v == (0.0, 0.0) for v in values):
        return None
    return values

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
        for _, data, _ in sorted(all_arrays, key=lambda x: x[0], reverse=True):
            if len(data) == 12 and all(isinstance(item, list) and len(item) >= 2 for item in data):
                values = []
                for item in data:
                    try:
                        if len(item) == 3 and isinstance(item[0], str):
                            min_val = max(-5, min(0, float(item[1])))
                            max_val = max(0, min(5, float(item[2])))
                        else:
                            min_val = max(-5, min(0, float(item[0])))
                            max_val = max(0, min(5, float(item[1])))
                        values.append((min_val, max_val))
                    except (ValueError, TypeError):
                        values.append((0.0, 0.0))
                return values
        for _, data, _ in sorted(all_arrays, key=lambda x: x[0], reverse=True):
            if len(data) == 12 and all(isinstance(item, (int, float)) for item in data):
                values = []
                for balance in data:
                    try:
                        balance = max(-5, min(5, float(balance)))
                        if balance >= 0:
                            min_val = 0
                            max_val = balance
                        else:
                            min_val = balance
                            max_val = 0
                        values.append((min_val, max_val))
                    except (ValueError, TypeError):
                        values.append((0.0, 0.0))
                return values
        logger.warning(f"[chart] No valid 12-element array found")
        logger.warning(f"[chart] Raw input: {raw[:300]}")
        return None
    except Exception as e:
        logger.warning(f"[chart] JSON parse failed: {e}")
        logger.warning(f"[chart] Raw input: {raw[:300]}")
        return None

def get_bar_color(balance: float) -> str:
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

def get_text_color_for_bar(bar_color: str) -> str:
    if bar_color in ["#00ff88", "#88ff00"]:
        return "#050810"
    else:
        return "#ffffff"

def value_to_y(v: float) -> int:
    normalized = (v + 5) / 10
    return int(CHART_BOTTOM - normalized * CHART_H)

def render_values_svg(values: List[Tuple[float, float]], title: str = "SENTIMENT ANALYSIS", subtitle: str = "") -> str:
    net_balance = sum((min_val + max_val) / 2 for min_val, max_val in values)
    positive_count = sum(1 for min_val, max_val in values if (min_val + max_val) / 2 > 0)
    negative_count = sum(1 for min_val, max_val in values if (min_val + max_val) / 2 < 0)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#050810"/>
      <stop offset="100%" style="stop-color:#0a1020"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" fill="url(#bg)"/>
  
  <text x="56" y="48" fill="#e7e7e7" font-family="Arial, sans-serif" font-size="20" font-weight="bold">P</text>
  <circle cx="81" cy="42" r="8" fill="#00ff88"/>
  <text x="93" y="48" fill="#e7e7e7" font-family="Arial, sans-serif" font-size="20" font-weight="bold">SITIVE: {positive_count}/12</text>
  
  <text x="512" y="48" text-anchor="middle" fill="#ffffff" font-family="Arial, sans-serif" font-size="36" font-weight="bold" letter-spacing="4">{title}</text>
  
  <text x="835" y="48" text-anchor="end" fill="#e7e7e7" font-family="Arial, sans-serif" font-size="20" font-weight="bold">NEGATI</text>
  <polygon points="838,32 854,32 846,50" fill="#ff3366"/>
  <text x="857" y="48" fill="#e7e7e7" font-family="Arial, sans-serif" font-size="20" font-weight="bold">E: {negative_count}/12</text>
  
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
        balance = (min_val + max_val) / 2
        x = CHART_LEFT + i * BAR_WIDTH + BAR_GAP / 2
        color = get_bar_color(balance)
        text_color = get_text_color_for_bar(color)
        
        min_y = value_to_y(min_val)
        max_y = value_to_y(max_val)
        
        if abs(min_val) > 0.01 or abs(max_val) > 0.01:
            if min_val < 0 and max_val > 0:
                neg_height = abs(zero_y - min_y)
                pos_height = abs(max_y - zero_y)
                svg += f'\n  <rect x="{x:.1f}" y="{zero_y}" width="{BAR_ACTUAL_W:.1f}" height="{neg_height}" fill="#ff3366" stroke="#ff3366" stroke-width="1" opacity="0.8"/>'
                svg += f'\n  <rect x="{x:.1f}" y="{max_y}" width="{BAR_ACTUAL_W:.1f}" height="{pos_height}" fill="#00ff88" stroke="#00ff88" stroke-width="1" opacity="0.8"/>'
                text_y = zero_y + neg_height / 2 + 5
            elif min_val < 0:
                bar_height = abs(min_y - zero_y)
                svg += f'\n  <rect x="{x:.1f}" y="{zero_y}" width="{BAR_ACTUAL_W:.1f}" height="{bar_height}" fill="{color}" stroke="{color}" stroke-width="1" opacity="0.8"/>'
                text_y = zero_y + bar_height / 2 + 5
            elif max_val > 0:
                bar_height = abs(zero_y - max_y)
                svg += f'\n  <rect x="{x:.1f}" y="{max_y}" width="{BAR_ACTUAL_W:.1f}" height="{bar_height}" fill="{color}" stroke="{color}" stroke-width="1" opacity="0.8"/>'
                text_y = max_y + bar_height / 2 + 5
            else:
                continue
            
            svg += f'\n  <text x="{x + BAR_ACTUAL_W/2:.1f}" y="{text_y:.1f}" text-anchor="middle" fill="{text_color}" font-family="Arial, sans-serif" font-size="14" font-weight="bold">{balance:+.1f}</text>'
    
    svg += '\n  <g font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="#c8d0e0">'
    for i, label in enumerate(VALUES):
        x = CHART_LEFT + i * BAR_WIDTH + BAR_WIDTH / 2
        abbr = VALUE_ABBR[label]
        svg += f'\n    <text x="{x:.1f}" y="{CHART_BOTTOM + 30}" text-anchor="middle">{abbr}</text>'
    svg += '\n  </g>'
    svg += f'\n  <g font-family="Arial, sans-serif" font-size="16" fill="#e7e7e7">'
    svg += f'\n    <text x="512" y="937" text-anchor="middle">NET: {net_balance:+.1f}</text>'
    svg += '\n    <text x="512" y="959" text-anchor="middle">Parameters relate to universal human values:</text>'
    legend_line1 = "LI - Life, FR - Freedom, JU - Justice, TR - Truth, SE - Security, PR - Prosperity"
    legend_line2 = "EQ - Equality, DI - Dignity, EN - Entertainment, SU - Sustainability, KN - Knowledge, SO - Solidarity"
    svg += f'\n    <text x="512" y="987" text-anchor="middle">{legend_line1}</text>'
    svg += f'\n    <text x="512" y="1015" text-anchor="middle">{legend_line2}</text>'
    svg += '\n  </g>'
    svg += '\n</svg>'
    return svg

def svg_to_png(svg_str: str, output_path: str = "chart_output.png") -> bytes:
    try:
        result = subprocess.run(
            ["rsvg-convert", "-w", "1024", "-h", "1024", "-d", "300", "-o", output_path],
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
    values = parse_bracket_format(values_json)
    if not values:
        values = parse_text_format(values_json)
    if not values:
        values = parse_inline_scores(values_json)
    if not values:
        values = parse_values_json(values_json)
    if not values:
        logger.error("[chart] Failed to parse values, returning None")
        return None
    svg = render_values_svg(values, title, subtitle)
    try:
        return svg_to_png(svg)
    except Exception as e:
        logger.warning(f"[chart] PNG render failed: {e}")
        return None
