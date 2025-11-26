#!/usr/bin/env python3
import argparse
import xml.etree.ElementTree as ET
from textwrap import shorten
from pathlib import Path
import html as html_mod
import re
from urllib.parse import urlparse

STATUS_RE = re.compile(r"\[(\d{3})\]")
KIND_RE = re.compile(r"- ([^\n\r]+)")
URL_RE = re.compile(r"https?://[^\s'\"]+")


def extract_base_url(curl_cmd: str, suite_name: str) -> str:
    """Извлекает базовый URL из curl команды или suite name."""
    # Сначала пробуем из curl
    if curl_cmd:
        url_match = URL_RE.search(curl_cmd)
        if url_match:
            full_url = url_match.group(0)
            # Убираем query параметры и путь, оставляем только базовый URL
            try:
                parsed = urlparse(full_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                return base_url
            except Exception:
                pass
    
    # Пробуем из suite_name (может содержать URL)
    if suite_name:
        url_match = URL_RE.search(suite_name)
        if url_match:
            full_url = url_match.group(0)
            try:
                parsed = urlparse(full_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                return base_url
            except Exception:
                pass
    
    return ""


def parse_junit(xml_path: Path):
    """Разбирает JUnit XML от Schemathesis и вытаскивает нужную инфу по ошибкам."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    issues = []

    for testsuite in root.findall("testsuite"):
        suite_name = testsuite.attrib.get("name", "")
        for tc in testsuite.findall("testcase"):
            tc_name = tc.attrib.get("name", "")
            time = tc.attrib.get("time", "")
            failure = tc.find("failure")
            if failure is None:
                continue

            raw_msg = failure.attrib.get("message", "").strip()

            # HTTP статус вида [500] / [400]
            m_status = STATUS_RE.search(raw_msg)
            status = m_status.group(1) if m_status else ""

            # Тип проблемы - первая строка после "- "
            m_kind = KIND_RE.search(raw_msg)
            kind = m_kind.group(1).strip() if m_kind else ""

            # Разделим на строки и вырежем блок с Reproduce with / curl
            lines = raw_msg.splitlines()
            clean_lines = []
            curl_cmd = ""
            seen_reproduce = False

            for line in lines:
                stripped = line.strip()

                # ловим заголовок "Reproduce with:"
                if stripped.lower().startswith("reproduce with"):
                    seen_reproduce = True
                    continue

                # первая строка с curl — запоминаем, но не показываем в основном тексте
                if stripped.startswith("curl "):
                    if not curl_cmd:
                        curl_cmd = stripped
                    # не добавляем в clean_lines
                    continue

                # если после "Reproduce with" идут ещё строки типа curl/пустые — скипаем
                if seen_reproduce and (stripped.startswith("curl ") or stripped == ""):
                    continue

                clean_lines.append(line)

            msg_clean = "\n".join(clean_lines).strip()
            if not msg_clean:
                msg_clean = raw_msg  # на всякий случай, если вдруг всё вырезали

            msg_short = shorten(msg_clean, width=180, placeholder="…")

            issues.append(
                {
                    "suite": suite_name,
                    "endpoint": tc_name,
                    "time": time,
                    "msg": msg_clean,      # уже без блока с curl
                    "msg_short": msg_short,
                    "status": status,
                    "kind": kind,
                    "curl": curl_cmd,      # сам curl вынут отдельно
                }
            )
    return issues


def status_pill_html(status: str) -> str:
    """Возвращает HTML бейджика для статуса."""
    if status.isdigit():
        code = int(status)
        if 500 <= code < 600:
            return f"<span class='pill pill-5xx'>{code}</span>"
        if 400 <= code < 500:
            return f"<span class='pill pill-4xx'>{code}</span>"
        if 200 <= code < 300:
            return f"<span class='pill pill-2xx'>{code}</span>"
    return "<span class='pill pill-unk'>n/a</span>"


def make_html(issues):
    total = len(issues)
    total_5xx = sum(
        1 for i in issues if i["status"].isdigit() and 500 <= int(i["status"]) < 600
    )
    total_4xx = sum(
        1 for i in issues if i["status"].isdigit() and 400 <= int(i["status"]) < 500
    )
    
    # Собираем уникальные базовые URL
    base_urls = set()
    for issue in issues:
        base_url = extract_base_url(issue.get("curl", ""), issue.get("suite", ""))
        if base_url:
            base_urls.add(base_url)
    base_urls = sorted(base_urls)  # Сортируем для консистентности
    
    # Вычисляем минимальное и максимальное время для ползунка
    times = []
    for issue in issues:
        try:
            time_val = float(issue["time"])
            times.append(time_val)
        except (ValueError, TypeError):
            continue
    
    min_time = min(times) if times else 0.0
    max_time = max(times) if times else 1.0

    # Формируем блок с URL и статистикой
    url_block = [
        "<div class='url-container'>",
        "<div style='display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap;'>",
    ]
    if base_urls:
        url_block.extend([
            "<div style='flex: 1; min-width: 200px;'>",
            "<div class='url-label'>🌐 Базовый URL</div>",
            "<div class='url-list'>",
        ])
        for url in base_urls:
            safe_url = html_mod.escape(url)
            url_block.append(
                f"<div class='url-badge'>"
                f"<svg class='url-icon' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'>"
                f"<path d='M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zM7 2v4H3V2h4zm6 0v4h-4V2h4zM3 10v4h4v-4H3zm10 0v4h-4v-4h4z' fill='currentColor' opacity='0.6'/>"
                f"</svg>{safe_url}</div>"
            )
        url_block.extend([
            "</div>",
            "</div>",
        ])
    url_block.extend([
        "<div style='flex: 1; min-width: 200px;'>",
        f"<div class='url-label'>📊 Статистика</div>",
        f"<div class='url-stats'>Всего ошибок: <strong>{total}</strong> · 5xx: <strong>{total_5xx}</strong> · 4xx: <strong>{total_4xx}</strong></div>",
        "</div>",
        "</div>",
        "</div>",
    ])

    parts = [
        "<!DOCTYPE html>",
        "<html lang='ru'>",
        "<head>",
        "<meta charset='UTF-8'/>",
        "<title>Reporthesis</title>",
        "<link rel='icon' type='image/svg+xml' href='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0nMzInIGhlaWdodD0nMzInIHZpZXdCb3g9JzAgMCAzMiAzMicgZmlsbD0nbm9uZScgeG1sbnM9J2h0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnJz4KPHJlY3Qgd2lkdGg9JzMyJyBoZWlnaHQ9JzMyJyByeD0nNicgZmlsbD0ndXJsKCNmYXZpY29uR3JhZGllbnQpJy8+CjxwYXRoIGQ9J004IDEwYzAtMS4xLjktMiAyLTJoMTJjMS4xIDAgMiAuOSAyIDJ2MTRjMCAxLjEtLjkgMi0yIDJIMTBjLTEuMSAwLTItLjktMi0yVjEwWicgZmlsbD0nd2hpdGUnIG9wYWNpdHk9JzAuMTUnLz4KPHBhdGggZD0nTTEwIDE0aDhNMTAgMThoNk0xMCAyMmg0JyBzdHJva2U9J3doaXRlJyBzdHJva2Utd2lkdGg9JzEuNScgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+CjxjaXJjbGUgY3g9JzI0JyBjeT0nMTQnIHI9JzQnIGZpbGw9J3doaXRlJyBvcGFjaXR5PScwLjknLz4KPHBhdGggZD0nTTIyIDE0bDEuNSAxLjVMMjYgMTMnIHN0cm9rZT0ndXJsKCNmYXZpY29uR3JhZGllbnQpJyBzdHJva2Utd2lkdGg9JzEuNScgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJyBzdHJva2UtbGluZWpvaW49J3JvdW5kJy8+CjxwYXRoIGQ9J00xOCAyNGwyIDIgNC00JyBzdHJva2U9J3doaXRlJyBzdHJva2Utd2lkdGg9JzInIHN0cm9rZS1saW5lY2FwPSdyb3VuZCcgc3Ryb2tlLWxpbmVqb2luPSdyb3VuZCcvPgo8ZGVmcz4KPGxpbmVhckdyYWRpZW50IGlkPSdmYXZpY29uR3JhZGllbnQnIHgxPScwJyB5MT0nMCcgeDI9JzMyJyB5Mj0nMzInIGdyYWRpZW50VW5pdHM9J3VzZXJTcGFjZU9uVXNlJz4KPHN0b3Agb2Zmc2V0PScwJScgc3RvcC1jb2xvcj0nIzNiODJmNicvPgo8c3RvcCBvZmZzZXQ9JzEwMCUnIHN0b3AtY29sb3I9JyMyNTYzZWInLz4KPC9saW5lYXJHcmFkaWVudD4KPC9kZWZzPgo8L3N2Zz4='/>",
        "<style>",
        # THEME VARIABLES
        ":root {",
        "  --bg: #0a0e1a;",
        "  --bg-alt: #111827;",
        "  --bg-gradient-end: #000000;",
        "  --text: #f3f4f6;",
        "  --text-muted: #9ca3af;",
        "  --border: #1f2937;",
        "  --border-light: #374151;",
        "  --hover: #1f2937;",
        "  --chip-bg: rgba(17, 24, 39, 0.6);",
        "  --header-bg: rgba(17, 24, 39, 0.95);",
        "  --row-even-bg: rgba(10, 14, 26, 0.5);",
        "  --row-odd-bg: rgba(17, 24, 39, 0.3);",
        "  --accent: #3b82f6;",
        "  --accent-hover: #60a5fa;",
        "  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);",
        "  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.4);",
        "  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.5);",
        "  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.6);",
        "  --shadow-2xl: 0 25px 50px -12px rgba(0, 0, 0, 0.7);",
        "}",
        "html.light {",
        "  --bg: #f8fafc;",
        "  --bg-alt: #ffffff;",
        "  --bg-gradient-end: #f1f5f9;",
        "  --text: #0f172a;",
        "  --text-muted: #64748b;",
        "  --border: #e2e8f0;",
        "  --border-light: #cbd5e1;",
        "  --hover: #f1f5f9;",
        "  --chip-bg: rgba(241, 245, 249, 0.8);",
        "  --header-bg: rgba(255, 255, 255, 0.95);",
        "  --row-even-bg: rgba(255, 255, 255, 0.5);",
        "  --row-odd-bg: rgba(248, 250, 252, 0.5);",
        "  --accent: #2563eb;",
        "  --accent-hover: #3b82f6;",
        "  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);",
        "  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);",
        "  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);",
        "  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1);",
        "  --shadow-2xl: 0 25px 50px -12px rgba(0, 0, 0, 0.15);",
        "}",
        "* { box-sizing: border-box; }",
        # общие стили
        "body { ",
        "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif; ",
        "  background: linear-gradient(135deg, var(--bg) 0%, var(--bg-alt) 50%, var(--bg-gradient-end) 100%); ",
        "  background-attachment: fixed; ",
        "  color: var(--text); ",
        "  margin: 0; ",
        "  padding: 32px 24px; ",
        "  min-height: 100vh; ",
        "  line-height: 1.6; ",
        "}",
        ".logo-container { ",
        "  display: flex; ",
        "  align-items: center; ",
        "  justify-content: center; ",
        "  flex-shrink: 0; ",
        "  transition: transform 0.3s ease; ",
        "  filter: drop-shadow(0 2px 4px rgba(59, 130, 246, 0.3)); ",
        "}",
        ".logo-container:hover { ",
        "  transform: scale(1.05) rotate(2deg); ",
        "  filter: drop-shadow(0 4px 8px rgba(59, 130, 246, 0.5)); ",
        "}",
        ".logo-svg { ",
        "  display: block; ",
        "}",
        "h1 { ",
        "  margin: 0; ",
        "  font-size: 32px; ",
        "  font-weight: 700; ",
        "  letter-spacing: -0.5px; ",
        "  background: linear-gradient(135deg, var(--text) 0%, var(--text-muted) 100%); ",
        "  -webkit-background-clip: text; ",
        "  -webkit-text-fill-color: transparent; ",
        "  background-clip: text; ",
        "}",
        ".meta { ",
        "  color: var(--text-muted); ",
        "  margin-bottom: 16px; ",
        "  font-size: 14px; ",
        "}",
        ".url-container { ",
        "  margin-bottom: 24px; ",
        "  padding: 16px 20px; ",
        "  background: var(--chip-bg); ",
        "  backdrop-filter: blur(10px); ",
        "  border-radius: 12px; ",
        "  border: 1px solid var(--border-light); ",
        "  box-shadow: var(--shadow-md); ",
        "}",
        ".url-label { ",
        "  font-size: 11px; ",
        "  color: var(--text-muted); ",
        "  text-transform: uppercase; ",
        "  letter-spacing: 0.5px; ",
        "  font-weight: 600; ",
        "  margin-bottom: 8px; ",
        "}",
        ".url-stats { ",
        "  font-size: 14px; ",
        "  color: var(--text); ",
        "  line-height: 1.5; ",
        "}",
        ".url-stats strong { ",
        "  color: var(--accent); ",
        "  font-weight: 600; ",
        "}",
        ".url-list { ",
        "  display: flex; ",
        "  flex-wrap: wrap; ",
        "  gap: 8px; ",
        "}",
        ".url-badge { ",
        "  display: inline-flex; ",
        "  align-items: center; ",
        "  gap: 6px; ",
        "  padding: 8px 14px; ",
        "  background: var(--bg-alt); ",
        "  border: 1px solid var(--border-light); ",
        "  border-radius: 8px; ",
        "  font-size: 13px; ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  color: var(--accent); ",
        "  box-shadow: var(--shadow-sm); ",
        "  transition: all 0.2s ease; ",
        "}",
        ".url-badge:hover { ",
        "  transform: translateY(-1px); ",
        "  box-shadow: var(--shadow-md); ",
        "  border-color: var(--accent); ",
        "}",
        ".url-icon { ",
        "  width: 14px; ",
        "  height: 14px; ",
        "  opacity: 0.7; ",
        "}",
        ".toolbar { ",
        "  display: flex; ",
        "  flex-wrap: wrap; ",
        "  gap: 16px; ",
        "  align-items: center; ",
        "  justify-content: space-between; ",
        "  margin-bottom: 24px; ",
        "  padding: 20px; ",
        "  background: var(--chip-bg); ",
        "  backdrop-filter: blur(10px); ",
        "  border-radius: 16px; ",
        "  border: 1px solid var(--border); ",
        "  box-shadow: var(--shadow-lg); ",
        "}",
        ".chips { ",
        "  display: flex; ",
        "  flex-wrap: wrap; ",
        "  gap: 10px; ",
        "}",
        ".chip { ",
        "  font-size: 12px; ",
        "  padding: 8px 16px; ",
        "  border-radius: 12px; ",
        "  border: 1px solid var(--border-light); ",
        "  background: var(--bg-alt); ",
        "  box-shadow: var(--shadow-sm); ",
        "  transition: all 0.2s ease; ",
        "  font-weight: 500; ",
        "}",
        ".chip:hover { ",
        "  transform: translateY(-1px); ",
        "  box-shadow: var(--shadow-md); ",
        "}",
        ".chip strong { ",
        "  color: var(--accent); ",
        "  font-weight: 700; ",
        "}",
        ".chip span { ",
        "  opacity: 0.8; ",
        "  margin-left: 4px; ",
        "}",
        ".filters { ",
        "  display: flex; ",
        "  flex-wrap: wrap; ",
        "  gap: 10px; ",
        "  align-items: center; ",
        "}",
        ".filter-btn { ",
        "  border-radius: 10px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 8px 16px; ",
        "  font-size: 12px; ",
        "  background: var(--bg-alt); ",
        "  color: var(--text); ",
        "  cursor: pointer; ",
        "  transition: all 0.2s ease; ",
        "  font-weight: 500; ",
        "  box-shadow: var(--shadow-sm); ",
        "}",
        ".filter-btn:hover { ",
        "  background: var(--hover); ",
        "  transform: translateY(-1px); ",
        "  box-shadow: var(--shadow-md); ",
        "}",
        ".filter-btn.active { ",
        "  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%); ",
        "  border-color: var(--accent); ",
        "  color: white; ",
        "  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); ",
        "}",
        ".search-input { ",
        "  background: var(--bg-alt); ",
        "  border-radius: 10px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 8px 16px; ",
        "  font-size: 13px; ",
        "  color: var(--text); ",
        "  transition: all 0.2s ease; ",
        "  box-shadow: var(--shadow-sm); ",
        "}",
        ".search-input:focus { ",
        "  outline: none; ",
        "  border-color: var(--accent); ",
        "  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1), var(--shadow-md); ",
        "}",
        ".search-input::placeholder { ",
        "  color: var(--text-muted); ",
        "}",
        # стили для ползунка времени
        ".time-filter-container { ",
        "  display: flex; ",
        "  align-items: center; ",
        "  gap: 10px; ",
        "  background: var(--bg-alt); ",
        "  border: 1px solid var(--border-light); ",
        "  border-radius: 12px; ",
        "  padding: 8px 14px; ",
        "  font-size: 12px; ",
        "  box-shadow: var(--shadow-sm); ",
        "}",
        ".time-filter-label { ",
        "  color: var(--text-muted); ",
        "  white-space: nowrap; ",
        "  font-weight: 500; ",
        "}",
        ".time-slider { ",
        "  flex: 1; ",
        "  min-width: 120px; ",
        "  max-width: 200px; ",
        "  height: 6px; ",
        "  background: var(--border); ",
        "  border-radius: 3px; ",
        "  outline: none; ",
        "  cursor: pointer; ",
        "  transition: all 0.2s ease; ",
        "}",
        ".time-slider:hover { ",
        "  background: var(--border-light); ",
        "}",
        ".time-slider::-webkit-slider-thumb { ",
        "  -webkit-appearance: none; ",
        "  appearance: none; ",
        "  width: 18px; ",
        "  height: 18px; ",
        "  border-radius: 50%; ",
        "  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%); ",
        "  cursor: pointer; ",
        "  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.4); ",
        "  transition: all 0.2s ease; ",
        "}",
        ".time-slider::-webkit-slider-thumb:hover { ",
        "  transform: scale(1.1); ",
        "  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.6); ",
        "}",
        ".time-slider::-moz-range-thumb { ",
        "  width: 18px; ",
        "  height: 18px; ",
        "  border-radius: 50%; ",
        "  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%); ",
        "  cursor: pointer; ",
        "  border: none; ",
        "  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.4); ",
        "  transition: all 0.2s ease; ",
        "}",
        ".time-slider::-moz-range-thumb:hover { ",
        "  transform: scale(1.1); ",
        "  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.6); ",
        "}",
        ".time-value { ",
        "  color: var(--accent); ",
        "  font-weight: 600; ",
        "  min-width: 60px; ",
        "  text-align: right; ",
        "}",
        # таблица
        "table { ",
        "  width: 100%; ",
        "  border-collapse: separate; ",
        "  border-spacing: 0; ",
        "  margin-top: 8px; ",
        "  font-size: 13px; ",
        "  border-radius: 16px; ",
        "  overflow: hidden; ",
        "  box-shadow: var(--shadow-2xl); ",
        "  background: var(--bg-alt); ",
        "  backdrop-filter: blur(10px); ",
        "}",
        "th, td { ",
        "  border-bottom: 1px solid var(--border); ",
        "  padding: 14px 12px; ",
        "  vertical-align: top; ",
        "}",
        "th { ",
        "  text-align: left; ",
        "  background: var(--header-bg); ",
        "  position: sticky; ",
        "  top: 0; ",
        "  z-index: 2; ",
        "  font-weight: 600; ",
        "  text-transform: uppercase; ",
        "  font-size: 11px; ",
        "  letter-spacing: 0.5px; ",
        "  color: var(--text-muted); ",
        "  backdrop-filter: blur(10px); ",
        "}",
        "tr.main-row { ",
        "  cursor: pointer; ",
        "  transition: all 0.2s ease; ",
        "}",
        "tr.main-row:hover td { ",
        "  background: var(--hover); ",
        "  transform: scale(1.001); ",
        "}",
        "tr.main-row.even td { ",
        "  background: var(--row-even-bg); ",
        "}",
        "tr.main-row.odd td { ",
        "  background: var(--row-odd-bg); ",
        "}",
        "tr.details-row td { ",
        "  background: var(--bg); ",
        "  padding-top: 12px; ",
        "  padding-bottom: 16px; ",
        "  animation: slideDown 0.3s ease; ",
        "}",
        "@keyframes slideDown { ",
        "  from { opacity: 0; transform: translateY(-10px); } ",
        "  to { opacity: 1; transform: translateY(0); } ",
        "}",
        ".endpoint { ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  font-size: 12px; ",
        "  color: var(--accent); ",
        "  font-weight: 500; ",
        "}",
        ".msg-short { ",
        "  white-space: pre-wrap; ",
        "  line-height: 1.5; ",
        "}",
        ".pill { ",
        "  display: inline-block; ",
        "  padding: 4px 10px; ",
        "  border-radius: 8px; ",
        "  font-size: 11px; ",
        "  margin-right: 6px; ",
        "  font-weight: 600; ",
        "  box-shadow: var(--shadow-sm); ",
        "  transition: all 0.2s ease; ",
        "}",
        ".pill:hover { ",
        "  transform: scale(1.05); ",
        "}",
        ".pill-5xx { ",
        "  background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); ",
        "  color: #fee2e2; ",
        "}",
        ".pill-4xx { ",
        "  background: linear-gradient(135deg, #ea580c 0%, #c2410c 100%); ",
        "  color: #ffedd5; ",
        "}",
        ".pill-2xx { ",
        "  background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); ",
        "  color: #dcfce7; ",
        "}",
        ".pill-unk { ",
        "  background: var(--border-light); ",
        "  color: var(--text); ",
        "}",
        ".kind { ",
        "  font-size: 11px; ",
        "  color: var(--text-muted); ",
        "  margin-top: 4px; ",
        "  font-style: italic; ",
        "}",
        ".details-box { ",
        "  border-radius: 12px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 16px; ",
        "  background: var(--bg-alt); ",
        "  box-shadow: var(--shadow-md); ",
        "}",
        ".details-box pre { ",
        "  margin: 12px 0 0 0; ",
        "  font-size: 12px; ",
        "  line-height: 1.6; ",
        "  white-space: pre-wrap; ",
        "  word-break: break-word; ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  color: var(--text); ",
        "}",
        ".details-header { ",
        "  display: flex; ",
        "  justify-content: space-between; ",
        "  align-items: center; ",
        "  gap: 12px; ",
        "  flex-wrap: wrap; ",
        "}",
        ".btn { ",
        "  border-radius: 10px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 8px 16px; ",
        "  font-size: 12px; ",
        "  background: var(--bg-alt); ",
        "  color: var(--text); ",
        "  cursor: pointer; ",
        "  transition: all 0.2s ease; ",
        "  font-weight: 500; ",
        "  box-shadow: var(--shadow-sm); ",
        "}",
        ".btn:hover { ",
        "  background: var(--hover); ",
        "  transform: translateY(-1px); ",
        "  box-shadow: var(--shadow-md); ",
        "}",
        ".btn:active { ",
        "  transform: translateY(0); ",
        "}",
        ".btn-execute { ",
        "  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%); ",
        "  border-color: var(--accent); ",
        "  color: white; ",
        "  font-weight: 600; ",
        "  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); ",
        "}",
        ".btn-execute:hover { ",
        "  background: linear-gradient(135deg, var(--accent-hover) 0%, var(--accent) 100%); ",
        "  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.5); ",
        "  transform: translateY(-2px); ",
        "}",
        ".btn-execute:active { ",
        "  transform: translateY(0); ",
        "  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.4); ",
        "}",
        ".btn-execute:disabled { ",
        "  opacity: 0.6; ",
        "  cursor: not-allowed; ",
        "  transform: none; ",
        "}",
        ".btn-copy { ",
        "  background: linear-gradient(135deg, #10b981 0%, #059669 100%); ",
        "  border-color: #10b981; ",
        "  color: white; ",
        "  font-weight: 600; ",
        "  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3); ",
        "}",
        ".btn-copy:hover { ",
        "  background: linear-gradient(135deg, #059669 0%, #10b981 100%); ",
        "  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.5); ",
        "  transform: translateY(-2px); ",
        "}",
        ".btn-copy:active { ",
        "  transform: translateY(0); ",
        "  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.4); ",
        "}",
        ".code-tag { ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  font-size: 11px; ",
        "  background: var(--bg); ",
        "  padding: 4px 8px; ",
        "  border-radius: 6px; ",
        "  border: 1px solid var(--border); ",
        "  color: var(--accent); ",
        "}",
        ".curl-row { ",
        "  display: flex; ",
        "  flex-wrap: wrap; ",
        "  gap: 10px; ",
        "  align-items: center; ",
        "  margin-top: 12px; ",
        "  padding-top: 12px; ",
        "  border-top: 1px solid var(--border); ",
        "}",
        ".curl-snippet { ",
        "  margin: 0; ",
        "  font-size: 12px; ",
        "  max-width: 100%; ",
        "  overflow-x: auto; ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  color: var(--text); ",
        "}",
        # модалка
        "#modal-backdrop { ",
        "  position: fixed; ",
        "  inset: 0; ",
        "  background: rgba(0, 0, 0, 0.75); ",
        "  backdrop-filter: blur(4px); ",
        "  display: none; ",
        "  align-items: center; ",
        "  justify-content: center; ",
        "  z-index: 50; ",
        "  animation: fadeIn 0.2s ease; ",
        "}",
        "@keyframes fadeIn { ",
        "  from { opacity: 0; } ",
        "  to { opacity: 1; } ",
        "}",
        "#modal { ",
        "  width: min(900px, 96%); ",
        "  max-height: 90vh; ",
        "  background: var(--bg-alt); ",
        "  border-radius: 20px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 24px; ",
        "  box-shadow: var(--shadow-2xl); ",
        "  display: flex; ",
        "  flex-direction: column; ",
        "  animation: slideUp 0.3s ease; ",
        "}",
        "@keyframes slideUp { ",
        "  from { opacity: 0; transform: translateY(20px) scale(0.95); } ",
        "  to { opacity: 1; transform: translateY(0) scale(1); } ",
        "}",
        "#modal-header { ",
        "  display: flex; ",
        "  justify-content: space-between; ",
        "  align-items: center; ",
        "  gap: 12px; ",
        "  margin-bottom: 16px; ",
        "  padding-bottom: 16px; ",
        "  border-bottom: 1px solid var(--border); ",
        "}",
        "#modal-title { ",
        "  font-size: 18px; ",
        "  font-weight: 700; ",
        "  letter-spacing: -0.3px; ",
        "}",
        "#modal-body { ",
        "  overflow: auto; ",
        "  flex: 1; ",
        "  display: flex; ",
        "  flex-direction: column; ",
        "  gap: 16px; ",
        "}",
        ".modal-info-grid { ",
        "  display: grid; ",
        "  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); ",
        "  gap: 12px; ",
        "}",
        ".modal-info-card { ",
        "  background: var(--bg-alt); ",
        "  border-radius: 10px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 12px 16px; ",
        "  box-shadow: var(--shadow-sm); ",
        "}",
        ".modal-info-label { ",
        "  font-size: 11px; ",
        "  color: var(--text-muted); ",
        "  text-transform: uppercase; ",
        "  letter-spacing: 0.5px; ",
        "  margin-bottom: 6px; ",
        "  font-weight: 600; ",
        "}",
        ".modal-info-value { ",
        "  font-size: 14px; ",
        "  color: var(--text); ",
        "  font-weight: 500; ",
        "  word-break: break-word; ",
        "}",
        ".modal-info-value.endpoint { ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  font-size: 12px; ",
        "  color: var(--accent); ",
        "}",
        ".modal-section { ",
        "  background: var(--bg); ",
        "  border-radius: 12px; ",
        "  border: 1px solid var(--border); ",
        "  padding: 16px; ",
        "}",
        ".modal-section-title { ",
        "  font-size: 13px; ",
        "  font-weight: 600; ",
        "  color: var(--text-muted); ",
        "  text-transform: uppercase; ",
        "  letter-spacing: 0.5px; ",
        "  margin-bottom: 12px; ",
        "  padding-bottom: 8px; ",
        "  border-bottom: 1px solid var(--border); ",
        "}",
        "#modal-body pre { ",
        "  margin: 0; ",
        "  font-size: 12px; ",
        "  line-height: 1.6; ",
        "  white-space: pre-wrap; ",
        "  word-break: break-word; ",
        "  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', 'Menlo', 'Consolas', 'DejaVu Sans Mono', monospace; ",
        "  background: var(--bg-alt); ",
        "  padding: 12px; ",
        "  border-radius: 8px; ",
        "  border: 1px solid var(--border-light); ",
        "}",
        ".modal-curl-section { ",
        "  display: flex; ",
        "  flex-wrap: wrap; ",
        "  gap: 10px; ",
        "  align-items: center; ",
        "  margin-top: 8px; ",
        "}",
        ".modal-curl-section pre { ",
        "  flex: 1; ",
        "  min-width: 300px; ",
        "  margin: 0; ",
        "}",
        ".close-btn { ",
        "  border-radius: 10px; ",
        "  border: 1px solid var(--border-light); ",
        "  padding: 6px 14px; ",
        "  font-size: 12px; ",
        "  background: var(--bg); ",
        "  color: var(--text); ",
        "  cursor: pointer; ",
        "  transition: all 0.2s ease; ",
        "  font-weight: 500; ",
        "}",
        ".close-btn:hover { ",
        "  background: var(--hover); ",
        "  transform: translateY(-1px); ",
        "}",
        # тост
        "#toast { ",
        "  position: fixed; ",
        "  bottom: 24px; ",
        "  right: 24px; ",
        "  background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); ",
        "  color: #ecfdf5; ",
        "  padding: 12px 20px; ",
        "  border-radius: 12px; ",
        "  font-size: 13px; ",
        "  font-weight: 500; ",
        "  box-shadow: var(--shadow-xl); ",
        "  display: none; ",
        "  z-index: 60; ",
        "  animation: slideInRight 0.3s ease; ",
        "}",
        "@keyframes slideInRight { ",
        "  from { opacity: 0; transform: translateX(100px); } ",
        "  to { opacity: 1; transform: translateX(0); } ",
        "}",
        "footer { ",
        "  text-align: center; ",
        "  margin-top: 48px; ",
        "  padding: 24px; ",
        "  color: var(--text-muted); ",
        "  font-size: 13px; ",
        "}",
        "footer a { ",
        "  color: var(--accent); ",
        "  text-decoration: none; ",
        "  border-bottom: 1px solid transparent; ",
        "  padding-bottom: 2px; ",
        "  transition: all 0.2s ease; ",
        "}",
        "footer a:hover { ",
        "  border-bottom-color: var(--accent); ",
        "  color: var(--accent-hover); ",
        "}",
        "</style>",
        "</head>",
        "<body>",
        "<div style='display: flex; align-items: center; gap: 12px; margin-bottom: 8px;'>",
        "<div class='logo-container' onclick='resetFilters()' style='cursor: pointer;' title='Сбросить все фильтры'>",
        "<svg width='48' height='48' viewBox='0 0 48 48' fill='none' xmlns='http://www.w3.org/2000/svg' class='logo-svg'>",
        "<rect width='48' height='48' rx='10' fill='url(#logoGradient)'/>",
        "<rect x='10' y='8' width='20' height='28' rx='2' fill='white' opacity='0.15'/>",
        "<path d='M14 16h12M14 22h12M14 28h8' stroke='white' stroke-width='2' stroke-linecap='round'/>",
        "<circle cx='32' cy='18' r='5' fill='white' opacity='0.95'/>",
        "<path d='M29.5 18l1.5 1.5 3-3' stroke='url(#logoGradient)' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>",
        "<path d='M28 32l2 2 4-4' stroke='white' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'/>",
        "<circle cx='8' cy='14' r='2' fill='white' opacity='0.7'/>",
        "<circle cx='8' cy='22' r='2' fill='white' opacity='0.7'/>",
        "<circle cx='8' cy='30' r='2' fill='white' opacity='0.7'/>",
        "<path d='M10 14l2-2M10 22l2-2M10 30l2-2' stroke='white' stroke-width='1.5' stroke-linecap='round' opacity='0.5'/>",
        "<circle cx='40' cy='14' r='2' fill='white' opacity='0.7'/>",
        "<circle cx='40' cy='22' r='2' fill='white' opacity='0.7'/>",
        "<circle cx='40' cy='30' r='2' fill='white' opacity='0.7'/>",
        "<path d='M38 14l-2-2M38 22l-2-2M38 30l-2-2' stroke='white' stroke-width='1.5' stroke-linecap='round' opacity='0.5'/>",
        "<defs>",
        "<linearGradient id='logoGradient' x1='0' y1='0' x2='48' y2='48' gradientUnits='userSpaceOnUse'>",
        "<stop offset='0%' stop-color='#3b82f6'/>",
        "<stop offset='100%' stop-color='#2563eb'/>",
        "</linearGradient>",
        "</defs>",
        "</svg>",
        "</div>",
        "<h1 style='margin: 0;'>Reporthesis</h1>",
        "</div>",
        *url_block,
        "<div class='toolbar'>",
        "<div class='chips'>",
        f"<div class='chip'><strong>{total}</strong> <span>запросов</span></div>",
        f"<div class='chip'><strong>{total_5xx}</strong> <span>5xx ошибок</span></div>",
        f"<div class='chip'><strong>{total_4xx}</strong> <span>4xx ошибок</span></div>",
        "</div>",
        "<div class='filters'>",
        "<button class='filter-btn active' data-mode='all' "
        "onclick='setFilter(event, \"all\")'>Все</button>",
        "<button class='filter-btn' data-mode='5xx' "
        "onclick='setFilter(event, \"5xx\")'>Только 5xx</button>",
        "<button class='filter-btn' data-mode='4xx' "
        "onclick='setFilter(event, \"4xx\")'>Только 4xx</button>",
        "<input class='search-input' id='search' type='text' "
        "placeholder='Фильтр по endpoint / тексту…' oninput='applySearch()'/>",
        f"<div class='time-filter-container'>",
        f"<span class='time-filter-label'>Время ≥</span>",
        f"<input type='range' class='time-slider' id='time-filter' "
        f"min='{min_time:.6f}' max='{max_time:.6f}' step='{max((max_time - min_time) / 1000, 0.000001):.6f}' "
        f"value='{min_time:.6f}' oninput='updateTimeFilter(this.value)'/>",
        f"<span class='time-value' id='time-value'>{min_time:.3f}s</span>",
        f"</div>",
        "<button class='btn' id='theme-toggle' type='button' onclick='toggleTheme()'>🌙 Тёмная</button>",
        "</div>",
        "</div>",
        "<p class='meta' style='margin-top: 16px; padding: 12px 16px; background: var(--bg-alt); border-radius: 10px; border: 1px solid var(--border); font-size: 12px; line-height: 1.6;'>",
        "💡 <strong>Советы:</strong> Клик по строке раскрывает подробности. "
        "Фильтрация работает по статусам, поиску по endpoint/тексту и времени выполнения. "
        "Кнопка «Скопировать curl» кладёт команду в буфер обмена. "
        "Кнопка «🌙/☀️» переключает тему.",
        "</p>",
        "</div>",
        "<table>",
        "<thead><tr><th>#</th><th>Статус</th><th>Эндпоинт</th><th>Время, s</th><th>Тест</th></tr></thead>",
        "<tbody>",
    ]

    for idx, issue in enumerate(issues, start=1):
        suite = issue["suite"]
        tc_name = issue["endpoint"]
        time = issue["time"]
        msg_short = issue["msg_short"]
        full = issue["msg"]          # уже без блока Reproduce/curl
        status = issue["status"]
        kind = issue["kind"]
        curl_cmd = issue["curl"]

        safe_suite = html_mod.escape(suite)
        safe_tc = html_mod.escape(tc_name)
        safe_time = html_mod.escape(time)
        safe_short = html_mod.escape(msg_short)
        safe_full = html_mod.escape(full, quote=False)
        safe_kind = html_mod.escape(kind)

        endpoint_lower = tc_name.lower()
        endpoint_attr = html_mod.escape(endpoint_lower, quote=True)

        data_status = status
        row_class = "even" if idx % 2 == 0 else "odd"

        # Получаем числовое значение времени для атрибута data-time
        try:
            time_float = float(time)
        except (ValueError, TypeError):
            time_float = 0.0
        
        parts.append(
            f"<tr class='main-row {row_class}' data-idx='{idx}' "
            f"data-status='{data_status}' "
            f"data-endpoint='{endpoint_attr}' "
            f"data-time='{time_float:.6f}' "
            f"onclick=\"toggleDetails({idx})\">"
        )
        parts.append(f"<td>{idx}</td>")
        parts.append(f"<td>{status_pill_html(status)}</td>")
        parts.append(f"<td class='endpoint'>{safe_tc}</td>")
        parts.append(f"<td>{safe_time}</td>")

        issue_cell = f"<div class='msg-short'>{safe_short}</div>"
        if kind:
            issue_cell += f"<div class='kind'>{safe_kind}</div>"
        parts.append(f"<td>{issue_cell}</td>")
        parts.append("</tr>")

        # details row
        safe_curl_attr = html_mod.escape(curl_cmd, quote=True) if curl_cmd else ""
        parts.append(
            f"<tr class='details-row' id='details-{idx}' style='display:none;' "
            f"data-status='{data_status}' "
            f"data-endpoint='{endpoint_attr}' "
            f"data-time='{safe_time}' "
            f"data-suite='{html_mod.escape(suite, quote=True)}' "
            f"data-kind='{html_mod.escape(kind, quote=True)}' "
            f"data-curl='{safe_curl_attr}'>"
        )
        parts.append("<td colspan='5'>")
        parts.append("<div class='details-box'>")
        parts.append("<div class='details-header'>")

        pill_html = status_pill_html(status)
        title_left = f"{pill_html} <span class='code-tag'>{safe_suite}</span>"
        parts.append(f"<div>{title_left}</div>")

        parts.append(
            f"<button class='btn' type='button' "
            f"onclick='openModalFromDetails(event, {idx})'>Открыть в отдельном окне</button>"
        )
        parts.append("</div>")

        parts.append(f"<pre id='details-pre-{idx}'>{safe_full}</pre>")

        if curl_cmd:
            safe_curl = html_mod.escape(curl_cmd)
            parts.append("<div class='curl-row'>")
            parts.append("<span class='code-tag'>curl</span>")
            parts.append(
                f"<pre class='curl-snippet' id='curl-{idx}'>{safe_curl}</pre>"
            )
            parts.append(
                f"<button class='btn btn-copy' type='button' "
                f"onclick='copyCurl(\"curl-{idx}\")'>Скопировать curl</button>"
            )
            parts.append(
                f"<button class='btn btn-execute' type='button' id='execute-curl-btn-{idx}' "
                f"onclick='executeCurlFromDetails({idx})'>Выполнить curl</button>"
            )
            parts.append("</div>")
            parts.append(
                f"<div id='curl-result-{idx}' style='display:none; margin-top: 16px; padding: 16px; background: var(--bg-alt); border-radius: 12px; border: 1px solid var(--border-light);'>"
            )
            parts.append(
                f"<div class='modal-section-title' style='margin-bottom: 12px;'>Результат выполнения</div>"
            )
            parts.append(
                f"<div id='curl-result-status-{idx}' style='margin-bottom: 12px;'></div>"
            )
            parts.append(
                f"<div id='curl-result-headers-{idx}' style='margin-bottom: 12px;'></div>"
            )
            parts.append(
                f"<pre id='curl-result-body-{idx}' style='margin: 0; max-height: 400px; overflow-y: auto;'></pre>"
            )
            parts.append("</div>")

        parts.append("</div>")
        parts.append("</td></tr>")

    # низ страницы + JS
    parts += [
        "</tbody></table>",
        "<div id='modal-backdrop' onclick='backdropClick(event)'>",
        "<div id='modal' onclick='event.stopPropagation()'>",
        "<div id='modal-header'>",
        "<div id='modal-title'>Подробности ошибки</div>",
        "<button class='close-btn' type='button' onclick='closeModal()'>Закрыть</button>",
        "</div>",
        "<div id='modal-body'>",
        "<div class='modal-info-grid' id='modal-info-grid'></div>",
        "<div class='modal-section'>",
        "<div class='modal-section-title'>Сообщение об ошибке</div>",
        "<pre id='modal-error-message'></pre>",
        "</div>",
        "<div class='modal-section' id='modal-curl-section' style='display:none;'>",
        "<div class='modal-section-title'>Curl команда</div>",
        "<div class='modal-curl-section'>",
        "<span class='code-tag'>curl</span>",
        "<pre id='modal-curl-command'></pre>",
        "<button class='btn btn-copy' type='button' onclick='copyModalCurl()'>Скопировать curl</button>",
        "<button class='btn btn-execute' type='button' id='execute-curl-btn' onclick='executeModalCurl()'>Выполнить curl</button>",
        "</div>",
        "<div id='modal-curl-result' style='display:none; margin-top: 16px; padding: 16px; background: var(--bg-alt); border-radius: 12px; border: 1px solid var(--border-light);'>",
        "<div class='modal-section-title' style='margin-bottom: 12px;'>Результат выполнения</div>",
        "<div id='curl-result-status' style='margin-bottom: 12px;'></div>",
        "<div id='curl-result-headers' style='margin-bottom: 12px;'></div>",
        "<pre id='curl-result-body' style='margin: 0; max-height: 400px; overflow-y: auto;'></pre>",
        "</div>",
        "</div>",
        "</div>",
        "</div>",
        "</div>",
        "<div id='toast'></div>",
        "<script>",
        "var currentFilter = 'all';",
        f"var minTimeValue = {min_time:.6f};",
        "function resetFilters() {",
        "  currentFilter = 'all';",
        "  var buttons = document.querySelectorAll('.filter-btn');",
        "  buttons.forEach(function(b){ b.classList.remove('active'); });",
        "  var allBtn = document.querySelector('.filter-btn[data-mode=\"all\"]');",
        "  if (allBtn) { allBtn.classList.add('active'); }",
        "  var searchInput = document.getElementById('search');",
        "  if (searchInput) { searchInput.value = ''; }",
        "  var timeFilter = document.getElementById('time-filter');",
        "  if (timeFilter) { timeFilter.value = minTimeValue; }",
        "  var timeValue = document.getElementById('time-value');",
        "  if (timeValue) { timeValue.textContent = minTimeValue.toFixed(3) + 's'; }",
        "  applyFilters();",
        "}",
        "function setFilter(ev, mode) {",
        "  currentFilter = mode;",
        "  var buttons = document.querySelectorAll('.filter-btn');",
        "  buttons.forEach(function(b){ b.classList.remove('active'); });",
        "  ev.target.classList.add('active');",
        "  applyFilters();",
        "}",
        "function updateTimeFilter(value) {",
        "  var timeValue = document.getElementById('time-value');",
        "  var val = parseFloat(value);",
        "  timeValue.textContent = val.toFixed(3) + 's';",
        "  applyFilters();",
        "}",
        "function applyFilters() {",
        "  var search = document.getElementById('search').value.toLowerCase();",
        "  var timeFilter = parseFloat(document.getElementById('time-filter').value);",
        "  var rows = document.querySelectorAll('tr.main-row');",
        "  rows.forEach(function(row){",
        "    var status = row.getAttribute('data-status');",
        "    var endpoint = row.getAttribute('data-endpoint') || '';",
        "    var text = row.innerText.toLowerCase();",
        "    var timeAttr = row.getAttribute('data-time');",
        "    var rowTime = parseFloat(timeAttr) || 0;",
        "    var matchFilter = true;",
        "    if (currentFilter === '5xx') {",
        "      matchFilter = status && parseInt(status) >= 500 && parseInt(status) < 600;",
        "    } else if (currentFilter === '4xx') {",
        "      matchFilter = status && parseInt(status) >= 400 && parseInt(status) < 500;",
        "    }",
        "    var matchSearch = !search || endpoint.indexOf(search) !== -1 || text.indexOf(search) !== -1;",
        "    var matchTime = rowTime >= timeFilter;",
        "    var show = matchFilter && matchSearch && matchTime;",
        "    row.style.display = show ? 'table-row' : 'none';",
        "    var idx = row.getAttribute('data-idx');",
        "    var details = document.getElementById('details-' + idx);",
        "    if (details && !show) { details.style.display = 'none'; }",
        "  });",
        "}",
        "function applySearch() { applyFilters(); }",
        "function toggleDetails(idx) {",
        "  var row = document.querySelector(\"tr.main-row[data-idx='\"+idx+\"']\");",
        "  if (!row || row.style.display === 'none') return;",
        "  var det = document.getElementById('details-' + idx);",
        "  if (!det) return;",
        "  det.style.display = (det.style.display === 'none' || det.style.display === '') ? 'table-row' : 'none';",
        "}",
        "function openModalFromDetails(event, idx) {",
        "  event.stopPropagation();",
        "  var detailsRow = document.getElementById('details-' + idx);",
        "  if (!detailsRow) return;",
        "  ",
        "  var status = detailsRow.getAttribute('data-status') || '';",
        "  var endpoint = detailsRow.getAttribute('data-endpoint') || '';",
        "  var time = detailsRow.getAttribute('data-time') || '';",
        "  var suite = detailsRow.getAttribute('data-suite') || '';",
        "  var kind = detailsRow.getAttribute('data-kind') || '';",
        "  var curl = detailsRow.getAttribute('data-curl') || '';",
        "  ",
        "  var pre = document.getElementById('details-pre-' + idx);",
        "  var errorMessage = pre ? (pre.textContent || pre.innerText) : '';",
        "  ",
        "  // Заполняем информационные карточки",
        "  var infoGrid = document.getElementById('modal-info-grid');",
        "  var statusHtml = '';",
        "  if (status) {",
        "    var code = parseInt(status);",
        "    if (500 <= code && code < 600) {",
        "      statusHtml = '<span class=\"pill pill-5xx\">' + status + '</span>';",
        "    } else if (400 <= code && code < 500) {",
        "      statusHtml = '<span class=\"pill pill-4xx\">' + status + '</span>';",
        "    } else if (200 <= code && code < 300) {",
        "      statusHtml = '<span class=\"pill pill-2xx\">' + status + '</span>';",
        "    } else {",
        "      statusHtml = '<span class=\"pill pill-unk\">' + status + '</span>';",
        "    }",
        "  } else {",
        "    statusHtml = '<span class=\"pill pill-unk\">n/a</span>';",
        "  }",
        "  ",
        "  infoGrid.innerHTML = ",
        "    '<div class=\"modal-info-card\">' +",
        "      '<div class=\"modal-info-label\">HTTP Статус</div>' +",
        "      '<div class=\"modal-info-value\">' + statusHtml + '</div>' +",
        "    '</div>' +",
        "    '<div class=\"modal-info-card\">' +",
        "      '<div class=\"modal-info-label\">Эндпоинт</div>' +",
        "      '<div class=\"modal-info-value endpoint\">' + (endpoint || '—') + '</div>' +",
        "    '</div>' +",
        "    '<div class=\"modal-info-card\">' +",
        "      '<div class=\"modal-info-label\">Время выполнения</div>' +",
        "      '<div class=\"modal-info-value\">' + (time ? time + 's' : '—') + '</div>' +",
        "    '</div>' +",
        "    '<div class=\"modal-info-card\">' +",
        "      '<div class=\"modal-info-label\">Test Suite</div>' +",
        "      '<div class=\"modal-info-value\">' + (suite || '—') + '</div>' +",
        "    '</div>' +",
        "    (kind ? '<div class=\"modal-info-card\">' +",
        "      '<div class=\"modal-info-label\">Тип ошибки</div>' +",
        "      '<div class=\"modal-info-value\">' + kind + '</div>' +",
        "    '</div>' : '');",
        "  ",
        "  // Заполняем сообщение об ошибке",
        "  document.getElementById('modal-error-message').textContent = errorMessage;",
        "  ",
        "  // Заполняем curl команду, если есть",
        "  var curlSection = document.getElementById('modal-curl-section');",
        "  var curlCommand = document.getElementById('modal-curl-command');",
        "  if (curl) {",
        "    curlCommand.textContent = curl;",
        "    curlSection.style.display = 'block';",
        "  } else {",
        "    curlSection.style.display = 'none';",
        "  }",
        "  ",
        "  document.getElementById('modal-backdrop').style.display = 'flex';",
        "}",
        "function copyModalCurl() {",
        "  var curlCommand = document.getElementById('modal-curl-command');",
        "  if (!curlCommand) return;",
        "  var text = curlCommand.textContent || curlCommand.innerText;",
        "  if (!text) return;",
        "  if (navigator.clipboard && navigator.clipboard.writeText) {",
        "    navigator.clipboard.writeText(text).then(function(){ showToast('curl скопирован'); }).catch(function(){ fallbackCopy(text); });",
        "  } else {",
        "    fallbackCopy(text);",
        "  }",
        "}",
        "function parseCurlCommand(curlStr) {",
        "  var result = { method: 'GET', url: '', headers: {}, body: null };",
        "  curlStr = curlStr.trim().replace(/\\\\\\n/g, ' ').replace(/\\s+/g, ' ');",
        "  if (!curlStr.startsWith('curl ')) { return null; }",
        "  ",
        "  var tokens = [];",
        "  var current = '';",
        "  var inQuotes = false;",
        "  var quoteChar = '';",
        "  for (var i = 5; i < curlStr.length; i++) {",
        "    var char = curlStr[i];",
        "    if ((char === '\"' || char === \"'\") && (i === 0 || curlStr[i-1] !== '\\\\')) {",
        "      if (!inQuotes) {",
        "        inQuotes = true;",
        "        quoteChar = char;",
        "        continue;",
        "      } else if (char === quoteChar) {",
        "        inQuotes = false;",
        "        quoteChar = '';",
        "        continue;",
        "      }",
        "    }",
        "    if (char === ' ' && !inQuotes) {",
        "      if (current.trim()) { tokens.push(current.trim()); }",
        "      current = '';",
        "    } else {",
        "      current += char;",
        "    }",
        "  }",
        "  if (current.trim()) { tokens.push(current.trim()); }",
        "  ",
        "  var i = 0;",
        "  while (i < tokens.length) {",
        "    var token = tokens[i];",
        "    if (token === '-X' || token === '--request') {",
        "      result.method = (tokens[++i] || 'GET').replace(/^[\"']|[\"']$/g, '');",
        "    } else if (token === '-H' || token === '--header') {",
        "      var headerStr = (tokens[++i] || '').replace(/^[\"']|[\"']$/g, '');",
        "      var headerMatch = headerStr.match(/^([^:]+):\\s*(.+)$/);",
        "      if (headerMatch) {",
        "        result.headers[headerMatch[1].trim()] = headerMatch[2].trim();",
        "      }",
        "    } else if (token === '-d' || token === '--data' || token === '--data-raw' || token === '--data-binary') {",
        "      var dataValue = (tokens[++i] || '').replace(/^[\"']|[\"']$/g, '');",
        "      if (dataValue) {",
        "        result.body = (result.body ? result.body + ' ' : '') + dataValue;",
        "      }",
        "    } else if (token.match(/^https?:\\/\\//)) {",
        "      result.url = token.replace(/^[\"']|[\"']$/g, '');",
        "    }",
        "    i++;",
        "  }",
        "  return result.url ? result : null;",
        "}",
        "function executeModalCurl() {",
        "  var curlCommand = document.getElementById('modal-curl-command');",
        "  if (!curlCommand) return;",
        "  var curlStr = curlCommand.textContent || curlCommand.innerText;",
        "  if (!curlStr) {",
        "    showToast('Нет curl команды');",
        "    return;",
        "  }",
        "  var parsed = parseCurlCommand(curlStr);",
        "  if (!parsed) {",
        "    showToast('Не удалось распарсить curl команду');",
        "    return;",
        "  }",
        "  var resultDiv = document.getElementById('modal-curl-result');",
        "  var statusDiv = document.getElementById('curl-result-status');",
        "  var headersDiv = document.getElementById('curl-result-headers');",
        "  var bodyDiv = document.getElementById('curl-result-body');",
        "  var executeBtn = document.getElementById('execute-curl-btn');",
        "  ",
        "  executeBtn.disabled = true;",
        "  executeBtn.textContent = 'Выполняется...';",
        "  resultDiv.style.display = 'block';",
        "  statusDiv.innerHTML = '<div style=\"color: var(--text-muted);\">Выполняется запрос...</div>';",
        "  headersDiv.innerHTML = '';",
        "  bodyDiv.textContent = '';",
        "  bodyDiv.style.color = '';",
        "  ",
        "  var unsupportedMethods = ['TRACE', 'CONNECT', 'TRACK'];",
        "  var methodUpper = parsed.method.toUpperCase();",
        "  if (unsupportedMethods.indexOf(methodUpper) !== -1) {",
        "    statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: Метод ' + parsed.method + ' не поддерживается браузером</div>' +",
        "      '<div style=\"color: var(--text-muted); font-size: 12px; margin-top: 8px;\">Методы TRACE, CONNECT и TRACK не поддерживаются Fetch API по соображениям безопасности.<br/>Выполните запрос напрямую через curl в терминале.</div>';",
        "    headersDiv.innerHTML = '';",
        "    bodyDiv.textContent = '';",
        "    bodyDiv.style.color = '#dc2626';",
        "    executeBtn.disabled = false;",
        "    executeBtn.textContent = 'Выполнить curl';",
        "    return;",
        "  }",
        "  ",
        "  var fetchOptions = {",
        "    method: parsed.method,",
        "    headers: parsed.headers,",
        "    mode: 'cors'",
        "  };",
        "  if (parsed.body) {",
        "    fetchOptions.body = parsed.body;",
        "  }",
        "  ",
        "  var startTime = Date.now();",
        "  fetch(parsed.url, fetchOptions)",
        "    .then(function(response) {",
        "      var endTime = Date.now();",
        "      var duration = ((endTime - startTime) / 1000).toFixed(3);",
        "      var statusColor = '';",
        "      if (response.status >= 500) {",
        "        statusColor = '#dc2626';",
        "      } else if (response.status >= 400) {",
        "        statusColor = '#ea580c';",
        "      } else if (response.status >= 200 && response.status < 300) {",
        "        statusColor = '#16a34a';",
        "      }",
        "      statusDiv.innerHTML = '<div style=\"font-weight: 600; margin-bottom: 8px;\">HTTP <span style=\"color: ' + statusColor + ';\">' + response.status + ' ' + response.statusText + '</span></div>' +",
        "        '<div style=\"color: var(--text-muted); font-size: 12px;\">Время выполнения: ' + duration + 's</div>';",
        "      ",
        "      var headersHtml = '<div style=\"font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;\">Заголовки ответа:</div><div style=\"font-family: monospace; font-size: 12px;\">';",
        "      response.headers.forEach(function(value, key) {",
        "        headersHtml += '<div style=\"margin-bottom: 4px;\"><strong>' + key + ':</strong> ' + value + '</div>';",
        "      });",
        "      headersHtml += '</div>';",
        "      headersDiv.innerHTML = headersHtml;",
        "      ",
        "      return response.text().catch(function() { return response.statusText; });",
        "    })",
        "    .then(function(text) {",
        "      try {",
        "        var json = JSON.parse(text);",
        "        bodyDiv.textContent = JSON.stringify(json, null, 2);",
        "      } catch(e) {",
        "        bodyDiv.textContent = text || '(пустой ответ)';",
        "      }",
        "      bodyDiv.style.color = '';",
        "      executeBtn.disabled = false;",
        "      executeBtn.textContent = 'Выполнить curl';",
        "    })",
        "    .catch(function(error) {",
        "      var endTime = Date.now();",
        "      var duration = ((endTime - startTime) / 1000).toFixed(3);",
        "      var errorMsg = error.message || String(error);",
        "      var errorStr = String(error);",
        "      if (errorStr.includes('unsupported') && (errorStr.includes('TRACE') || errorStr.includes('CONNECT') || errorStr.includes('TRACK'))) {",
        "        var methodMatch = errorStr.match(/('|\\\")(TRACE|CONNECT|TRACK)\\1/);",
        "        var method = methodMatch ? methodMatch[2] : 'этот метод';",
        "        statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: Метод ' + method + ' не поддерживается браузером</div>' +",
        "          '<div style=\"color: var(--text-muted); font-size: 12px; margin-top: 8px;\">Методы TRACE, CONNECT и TRACK не поддерживаются Fetch API по соображениям безопасности.<br/>Выполните запрос напрямую через curl в терминале.</div>';",
        "        headersDiv.innerHTML = '';",
        "        bodyDiv.textContent = 'Метод ' + method + ' не может быть выполнен через Fetch API. Используйте curl в терминале.';",
        "      } else if (errorMsg.includes('CORS') || errorMsg.includes('cors') || errorMsg.includes('network')) {",
        "        errorMsg = 'Ошибка CORS: Сервер не разрешает запросы с этого источника. Возможно, нужно использовать прокси или выполнить запрос с сервера.';",
        "        statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: ' + errorMsg + '</div>' +",
        "          '<div style=\"color: var(--text-muted); font-size: 12px;\">Время выполнения: ' + duration + 's</div>';",
        "        headersDiv.innerHTML = '';",
        "        bodyDiv.textContent = error.stack || error.message || String(error);",
        "      } else {",
        "        statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: ' + errorMsg + '</div>' +",
        "          '<div style=\"color: var(--text-muted); font-size: 12px;\">Время выполнения: ' + duration + 's</div>';",
        "        headersDiv.innerHTML = '';",
        "        bodyDiv.textContent = error.stack || error.message || String(error);",
        "      }",
        "      bodyDiv.style.color = '#dc2626';",
        "      executeBtn.disabled = false;",
        "      executeBtn.textContent = 'Выполнить curl';",
        "    });",
        "}",
        "function executeCurlFromDetails(idx) {",
        "  var curlEl = document.getElementById('curl-' + idx);",
        "  if (!curlEl) return;",
        "  var curlStr = curlEl.textContent || curlEl.innerText;",
        "  if (!curlStr) {",
        "    showToast('Нет curl команды');",
        "    return;",
        "  }",
        "  var parsed = parseCurlCommand(curlStr);",
        "  if (!parsed) {",
        "    showToast('Не удалось распарсить curl команду');",
        "    return;",
        "  }",
        "  var resultDiv = document.getElementById('curl-result-' + idx);",
        "  var statusDiv = document.getElementById('curl-result-status-' + idx);",
        "  var headersDiv = document.getElementById('curl-result-headers-' + idx);",
        "  var bodyDiv = document.getElementById('curl-result-body-' + idx);",
        "  var executeBtn = document.getElementById('execute-curl-btn-' + idx);",
        "  ",
        "  executeBtn.disabled = true;",
        "  executeBtn.textContent = 'Выполняется...';",
        "  resultDiv.style.display = 'block';",
        "  statusDiv.innerHTML = '<div style=\"color: var(--text-muted);\">Выполняется запрос...</div>';",
        "  headersDiv.innerHTML = '';",
        "  bodyDiv.textContent = '';",
        "  bodyDiv.style.color = '';",
        "  ",
        "  var unsupportedMethods = ['TRACE', 'CONNECT', 'TRACK'];",
        "  var methodUpper = parsed.method.toUpperCase();",
        "  if (unsupportedMethods.indexOf(methodUpper) !== -1) {",
        "    statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: Метод ' + parsed.method + ' не поддерживается браузером</div>' +",
        "      '<div style=\"color: var(--text-muted); font-size: 12px; margin-top: 8px;\">Методы TRACE, CONNECT и TRACK не поддерживаются Fetch API по соображениям безопасности.<br/>Выполните запрос напрямую через curl в терминале.</div>';",
        "    headersDiv.innerHTML = '';",
        "    bodyDiv.textContent = '';",
        "    bodyDiv.style.color = '#dc2626';",
        "    executeBtn.disabled = false;",
        "    executeBtn.textContent = 'Выполнить curl';",
        "    return;",
        "  }",
        "  ",
        "  var fetchOptions = {",
        "    method: parsed.method,",
        "    headers: parsed.headers,",
        "    mode: 'cors'",
        "  };",
        "  if (parsed.body) {",
        "    fetchOptions.body = parsed.body;",
        "  }",
        "  ",
        "  var startTime = Date.now();",
        "  fetch(parsed.url, fetchOptions)",
        "    .then(function(response) {",
        "      var endTime = Date.now();",
        "      var duration = ((endTime - startTime) / 1000).toFixed(3);",
        "      var statusColor = '';",
        "      if (response.status >= 500) {",
        "        statusColor = '#dc2626';",
        "      } else if (response.status >= 400) {",
        "        statusColor = '#ea580c';",
        "      } else if (response.status >= 200 && response.status < 300) {",
        "        statusColor = '#16a34a';",
        "      }",
        "      statusDiv.innerHTML = '<div style=\"font-weight: 600; margin-bottom: 8px;\">HTTP <span style=\"color: ' + statusColor + ';\">' + response.status + ' ' + response.statusText + '</span></div>' +",
        "        '<div style=\"color: var(--text-muted); font-size: 12px;\">Время выполнения: ' + duration + 's</div>';",
        "      ",
        "      var headersHtml = '<div style=\"font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;\">Заголовки ответа:</div><div style=\"font-family: monospace; font-size: 12px;\">';",
        "      response.headers.forEach(function(value, key) {",
        "        headersHtml += '<div style=\"margin-bottom: 4px;\"><strong>' + key + ':</strong> ' + value + '</div>';",
        "      });",
        "      headersHtml += '</div>';",
        "      headersDiv.innerHTML = headersHtml;",
        "      ",
        "      return response.text().catch(function() { return response.statusText; });",
        "    })",
        "    .then(function(text) {",
        "      try {",
        "        var json = JSON.parse(text);",
        "        bodyDiv.textContent = JSON.stringify(json, null, 2);",
        "      } catch(e) {",
        "        bodyDiv.textContent = text || '(пустой ответ)';",
        "      }",
        "      bodyDiv.style.color = '';",
        "      executeBtn.disabled = false;",
        "      executeBtn.textContent = 'Выполнить curl';",
        "    })",
        "    .catch(function(error) {",
        "      var endTime = Date.now();",
        "      var duration = ((endTime - startTime) / 1000).toFixed(3);",
        "      var errorMsg = error.message || String(error);",
        "      var errorStr = String(error);",
        "      if (errorStr.includes('unsupported') && (errorStr.includes('TRACE') || errorStr.includes('CONNECT') || errorStr.includes('TRACK'))) {",
        "        var methodMatch = errorStr.match(/('|\\\")(TRACE|CONNECT|TRACK)\\1/);",
        "        var method = methodMatch ? methodMatch[2] : 'этот метод';",
        "        statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: Метод ' + method + ' не поддерживается браузером</div>' +",
        "          '<div style=\"color: var(--text-muted); font-size: 12px; margin-top: 8px;\">Методы TRACE, CONNECT и TRACK не поддерживаются Fetch API по соображениям безопасности.<br/>Выполните запрос напрямую через curl в терминале.</div>';",
        "        headersDiv.innerHTML = '';",
        "        bodyDiv.textContent = 'Метод ' + method + ' не может быть выполнен через Fetch API. Используйте curl в терминале.';",
        "      } else if (errorMsg.includes('CORS') || errorMsg.includes('cors') || errorMsg.includes('network')) {",
        "        errorMsg = 'Ошибка CORS: Сервер не разрешает запросы с этого источника. Возможно, нужно использовать прокси или выполнить запрос с сервера.';",
        "        statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: ' + errorMsg + '</div>' +",
        "          '<div style=\"color: var(--text-muted); font-size: 12px;\">Время выполнения: ' + duration + 's</div>';",
        "        headersDiv.innerHTML = '';",
        "        bodyDiv.textContent = error.stack || error.message || String(error);",
        "      } else {",
        "        statusDiv.innerHTML = '<div style=\"font-weight: 600; color: #dc2626; margin-bottom: 8px;\">Ошибка: ' + errorMsg + '</div>' +",
        "          '<div style=\"color: var(--text-muted); font-size: 12px;\">Время выполнения: ' + duration + 's</div>';",
        "        headersDiv.innerHTML = '';",
        "        bodyDiv.textContent = error.stack || error.message || String(error);",
        "      }",
        "      bodyDiv.style.color = '#dc2626';",
        "      executeBtn.disabled = false;",
        "      executeBtn.textContent = 'Выполнить curl';",
        "    });",
        "}",
        "function closeModal() {",
        "  document.getElementById('modal-backdrop').style.display = 'none';",
        "  var resultDiv = document.getElementById('modal-curl-result');",
        "  if (resultDiv) { resultDiv.style.display = 'none'; }",
        "}",
        "function backdropClick(event) {",
        "  closeModal();",
        "}",
        "function showToast(msg) {",
        "  var t = document.getElementById('toast');",
        "  t.textContent = msg;",
        "  t.style.display = 'block';",
        "  setTimeout(function(){ t.style.display = 'none'; }, 1800);",
        "}",
        "function copyCurl(id) {",
        "  var el = document.getElementById(id);",
        "  if (!el) return;",
        "  var text = el.textContent || el.innerText;",
        "  if (navigator.clipboard && navigator.clipboard.writeText) {",
        "    navigator.clipboard.writeText(text).then(function(){ showToast('curl скопирован'); }).catch(function(){ fallbackCopy(text); });",
        "  } else {",
        "    fallbackCopy(text);",
        "  }",
        "}",
        "function fallbackCopy(text) {",
        "  var textarea = document.createElement('textarea');",
        "  textarea.value = text;",
        "  textarea.style.position = 'fixed';",
        "  textarea.style.left = '-9999px';",
        "  document.body.appendChild(textarea);",
        "  textarea.focus();",
        "  textarea.select();",
        "  try { document.execCommand('copy'); showToast('curl скопирован'); } catch(e) {}",
        "  document.body.removeChild(textarea);",
        "}",
        # theme system
        "function applyTheme(theme) {",
        "  if (theme === 'light') {",
        "    document.documentElement.classList.add('light');",
        "  } else {",
        "    document.documentElement.classList.remove('light');",
        "  }",
        "  localStorage.setItem('theme', theme);",
        "  var btn = document.getElementById('theme-toggle');",
        "  if (!btn) return;",
        "  btn.textContent = theme === 'light' ? '🌙 Тёмная' : '☀️ Светлая';",
        "}",
        "function toggleTheme() {",
        "  var current = localStorage.getItem('theme') || 'dark';",
        "  var next = current === 'light' ? 'dark' : 'light';",
        "  applyTheme(next);",
        "}",
        "document.addEventListener('DOMContentLoaded', function() {",
        "  var saved = localStorage.getItem('theme') || 'dark';",
        "  applyTheme(saved);",
        "});",
        "</script>",
        "<footer>",
        "<a href='https://github.com/dandreyanov'>Andreyanov Denis</a>",
        "</footer>",
        "</body></html>",
    ]

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Reporthesis — преобразует JUnit-отчёт Schemathesis в интерактивный HTML."
    )
    parser.add_argument(
        "junit_xml", help="Путь к JUnit XML (например, schemathesis-junit.xml)"
    )
    parser.add_argument(
        "-o",
        "--output",
        default="reporthesis.html",
        help="Имя выходного HTML-файла (по умолчанию reporthesis.html)",
    )
    args = parser.parse_args()

    xml_path = Path(args.junit_xml)
    issues = parse_junit(xml_path)
    html = make_html(issues)

    out_path = Path(args.output)
    out_path.write_text(html, encoding="utf-8")
    print(f"Готово! HTML-отчёт: {out_path.resolve()}")


if __name__ == "__main__":
    main()
