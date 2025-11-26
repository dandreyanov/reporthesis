# Reporthesis

## 🇷🇺 Описание
Reporthesis превращает JUnit-отчёты [Schemathesis](https://schemathesis.readthedocs.io/en/stable/) в стильный интерактивный HTML-дашборд. Скрипт вытягивает все неудачные тесты, группирует их по эндпоинтам и позволяет мгновенно провалиться в детали, не покидая браузер.

### Особенности
- фильтрация по статусам 5xx/4xx, поиску по endpoint и длительности теста;
- компактные карточки с расшифровкой ошибки, временем выполнения и test suite;
- модальное окно с полным текстом ошибки и кнопкой «Скопировать curl»;
- тёмная/светлая тема, адаптивная верстка и полностью офлайн-режим (все стили и скрипты встроены).

### Быстрый старт
```bash
python3 junit_to_html.py schemathesis-junit.xml -o reporthesis.html
open reporthesis.html
```

### Требования
- Python 3.8+
- JUnit XML от Schemathesis (CLI или pytest-плагин)

## 🇬🇧 Overview
Reporthesis turns [Schemathesis](https://schemathesis.readthedocs.io/en/stable/) JUnit reports into a sleek, interactive HTML dashboard. Failed checks are parsed, grouped by endpoint, and presented with instant drill-down without leaving the browser.

### Highlights
- status filters (5xx/4xx), full-text & endpoint search, and execution-time slider;
- concise failure cards with suite names, timings, and status badges;
- modal view with full error message plus one-click “Copy curl”;
- built-in light/dark theme, responsive layout, and fully offline bundle of CSS/JS.

### Quick start
```bash
python3 junit_to_html.py schemathesis-junit.xml -o reporthesis.html
open reporthesis.html
```

### Requirements
- Python 3.8+
- Schemathesis-generated JUnit XML (CLI or pytest plugin)

