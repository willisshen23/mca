from __future__ import annotations

import re
from functools import lru_cache

from bs4 import BeautifulSoup, Tag


def detect_layout_antipatterns(html: str) -> list[dict]:
    """Detect common ECharts layout anti-patterns in generated HTML reports.

    Returns a list of findings, each with keys: type, chart_id, detail.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []

    findings: list[dict] = []
    chart_divs = soup.find_all(
        "div", id=lambda x: x and x.lower().startswith("chart")
    )

    for chart_div in chart_divs:
        if not isinstance(chart_div, Tag):
            continue

        chart_id = chart_div.get("id", "")
        style = chart_div.get("style", "")
        styles = _parse_inline_styles(style)

        # Anti-pattern 1: chart div is a direct child of a flex container.
        parent = chart_div.find_parent()
        if parent and isinstance(parent, Tag) and _is_flex_container(parent):
            findings.append(
                {
                    "type": "flex_direct_chart",
                    "chart_id": chart_id,
                    "detail": "ECharts container is a direct flex item without a wrapper",
                }
            )

        # Anti-pattern 2: percentage height.
        height = styles.get("height", "")
        if "%" in height:
            findings.append(
                {
                    "type": "percentage_height",
                    "chart_id": chart_id,
                    "detail": "ECharts container uses percentage height",
                }
            )

        # Anti-pattern 3: missing explicit height.
        if not height:
            findings.append(
                {
                    "type": "missing_height",
                    "chart_id": chart_id,
                    "detail": "ECharts container has no explicit height",
                }
            )

        # Anti-pattern 4: missing width:100%.
        width = styles.get("width", "")
        if width and width != "100%":
            findings.append(
                {
                    "type": "non_full_width",
                    "chart_id": chart_id,
                    "detail": f"ECharts container width is {width} instead of 100%",
                }
            )

    return findings


def auto_fix_chart_layout(html: str) -> str:
    """Apply safe automatic fixes to ECharts layout anti-patterns.

    Fixes are idempotent and only touch ECharts container divs (ids starting
    with 'chart'). They do not rewrite user-provided CSS classes unless
    necessary.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    chart_divs = soup.find_all(
        "div", id=lambda x: x and x.lower().startswith("chart")
    )
    if not chart_divs:
        return html

    for chart_div in chart_divs:
        if not isinstance(chart_div, Tag):
            continue

        style = chart_div.get("style", "")
        styles = _parse_inline_styles(style)

        # Normalize width and box model.
        styles["width"] = "100%"
        styles["box-sizing"] = "border-box"
        styles["max-width"] = "100%"
        styles["min-width"] = "0"

        # Normalize height: default to 360px, replace percentage.
        height = styles.get("height", "")
        if not height or "%" in height:
            styles["height"] = "360px"

        # Mark as echarts-container for frontend selectors.
        chart_div["class"] = _merge_classes(chart_div.get("class", []), "echarts-container")
        chart_div["style"] = _serialize_inline_styles(styles)

        # Wrap direct flex children.
        parent = chart_div.find_parent()
        if parent and isinstance(parent, Tag) and _is_flex_container(parent):
            wrapper = soup.new_tag("div")
            wrapper["class"] = "chart-wrapper"
            wrapper["style"] = "min-width:0; max-width:100%; flex:1 1 auto; overflow:hidden;"
            chart_div.wrap(wrapper)

    return str(soup)


_CARD_STYLE_PATTERN = re.compile(r"box-shadow|border-radius|background", re.IGNORECASE)

_CONTAINER_RESET_PROPS = (
    "display",
    "flex-direction",
    "flex-wrap",
    "justify-content",
    "justify-items",
    "align-items",
    "align-content",
    "grid-template-columns",
    "gap",
    "row-gap",
    "column-gap",
)
_CHILD_RESET_PROPS = (
    "width",
    "min-width",
    "max-width",
    "flex",
    "flex-basis",
    "flex-grow",
    "flex-shrink",
    "margin",
    "margin-left",
    "margin-right",
    "margin-top",
    "margin-bottom",
)


def normalize_metric_card_layout(html: str) -> str:
    """Normalize metric-card groups so cards flow in one even grid.

    Generated reports often split metric cards into manual rows (e.g. five
    per row), leaving a single card stretched across the final row. This
    merges consecutive card rows into one container and rewrites it as a
    ``grid`` with ``auto-fill`` columns, so every card keeps the same width
    and leftover cards never stretch full-width.

    Fixes are conservative: only containers whose children all look like
    small, uniformly structured metric cards are touched. Idempotent.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    cardish_classes = _extract_card_style_classes(_style_tag_css_text(soup))
    containers = [
        el for el in soup.find_all(True) if _is_card_container(el, cardish_classes)
    ]
    if not containers:
        return html

    container_ids = {id(el) for el in containers}
    containers = [
        el
        for el in containers
        if not any(id(parent) in container_ids for parent in el.parents)
    ]

    removed: set[int] = set()
    for container in containers:
        sibling = _next_element_sibling(container)
        while (
            sibling is not None
            and _is_card_row(sibling, cardish_classes, min_children=1)
            and _card_kind(container) == _card_kind(sibling)
        ):
            following = _next_element_sibling(sibling)
            for child in list(_element_children(sibling)):
                container.append(child.extract())
            removed.add(id(sibling))
            sibling.decompose()
            sibling = following

    for container in containers:
        if id(container) in removed:
            continue
        child_count = len(_element_children(container))
        # Many cards: auto-fill keeps leftover cards at the same width as the
        # others instead of stretching them across the final row. Few cards
        # (a single row): auto-fit collapses empty tracks so the cards share
        # the full row width evenly instead of leaving blank space.
        columns = (
            "repeat(auto-fill, minmax(220px, 1fr))"
            if child_count >= 5
            else "repeat(auto-fit, minmax(260px, 1fr))"
        )
        _apply_grid_container_style(container, columns)
        for child in _element_children(container):
            _apply_grid_item_style(child)

    return str(soup)


def normalize_content_card_layout(html: str) -> str:
    """Stretch side-by-side content cards so each row fills its width.

    Comparison/insight cards are often emitted as a flex row with fixed
    pixel widths, leaving the right half of the row empty. Flex rows of 2-6
    uniformly structured cards are rewritten as ``grid`` with ``auto-fit``
    columns so the cards share the full row width evenly.

    Only flex rows are touched (an explicit "side by side" intent); stacked
    blocks, tables, charts and already-normalized grids are left alone.
    Idempotent.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    cardish_classes = _extract_card_style_classes(_style_tag_css_text(soup))
    changed = False
    for el in soup.find_all(True):
        if not _is_content_card_row(el, cardish_classes):
            continue
        _apply_grid_container_style(el, "repeat(auto-fit, minmax(320px, 1fr))")
        for child in _element_children(el):
            _apply_grid_item_style(child)
        changed = True

    return str(soup) if changed else html


def _is_content_card_row(el: Tag, cardish_classes: frozenset[str]) -> bool:
    if not _is_flex_container(el):
        return False
    children = _element_children(el)
    if not 2 <= len(children) <= 6:
        return False
    first_tag = children[0].name
    if any(child.name != first_tag for child in children):
        return False
    return all(_is_content_card(child, cardish_classes) for child in children)


def _is_content_card(el: Tag, cardish_classes: frozenset[str]) -> bool:
    text = el.get_text(" ", strip=True)
    if not text or len(text) > 400:
        return False
    if el.find(["script", "table", "iframe", "img", "video", "canvas", "form", "button"]):
        return False
    if el.find(id=lambda value: value and str(value).lower().startswith("chart")):
        return False
    if len(_element_children(el)) < 2:
        return False
    return _has_card_styling(el, cardish_classes)


def _element_children(tag: Tag) -> list[Tag]:
    return [child for child in tag.children if isinstance(child, Tag)]


def _next_element_sibling(tag: Tag) -> Tag | None:
    for sibling in tag.next_siblings:
        if isinstance(sibling, Tag):
            return sibling
        if str(sibling).strip():
            return None
    return None


def _is_card_container(el: Tag, cardish_classes: frozenset[str]) -> bool:
    return _is_card_row(el, cardish_classes, min_children=2)


def _is_card_row(el: Tag, cardish_classes: frozenset[str], min_children: int) -> bool:
    children = _element_children(el)
    if len(children) < min_children:
        return False
    first_tag = children[0].name
    if any(child.name != first_tag for child in children):
        return False
    return all(_is_metric_card(child, cardish_classes) for child in children)


def _is_metric_card(el: Tag, cardish_classes: frozenset[str]) -> bool:
    text = el.get_text(" ", strip=True)
    if not text or len(text) > 120:
        return False
    if not any(char.isdigit() for char in text):
        return False
    if el.find(["script", "table", "iframe", "img", "video", "canvas", "form", "button"]):
        return False
    if el.find(["h1", "h2", "h3"]):
        return False
    if el.find(id=lambda value: value and str(value).lower().startswith("chart")):
        return False
    return _has_card_styling(el, cardish_classes)


def _has_card_styling(el: Tag, cardish_classes: frozenset[str]) -> bool:
    if _CARD_STYLE_PATTERN.search(el.get("style", "")):
        return True
    classes = el.get("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    return any(cls in cardish_classes for cls in classes)


def _card_kind(container: Tag) -> tuple:
    signatures = []
    for child in _element_children(container):
        classes = child.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        signatures.append((child.name, frozenset(classes)))
    if not signatures:
        return ("", frozenset())
    tag_name = signatures[0][0]
    common = max(
        {sig for _, sig in signatures},
        key=lambda sig: sum(1 for _, other in signatures if other == sig),
    )
    return (tag_name, common)


def _apply_grid_container_style(container: Tag, columns: str) -> None:
    styles = _parse_inline_styles(container.get("style", ""))
    for prop in _CONTAINER_RESET_PROPS:
        styles.pop(prop, None)
    styles["display"] = "grid"
    styles["grid-template-columns"] = columns
    styles["gap"] = "16px"
    styles["align-items"] = "stretch"
    container["style"] = _serialize_inline_styles(styles)


def _apply_grid_item_style(child: Tag) -> None:
    styles = _parse_inline_styles(child.get("style", ""))
    for prop in _CHILD_RESET_PROPS:
        styles.pop(prop, None)
    styles["width"] = "auto"
    styles["max-width"] = "none"
    styles["margin"] = "0"
    child["style"] = _serialize_inline_styles(styles)


@lru_cache(maxsize=None)
def _extract_card_style_classes(css_text: str) -> frozenset[str]:
    """Scan CSS text for class selectors that give an element card styling."""
    card_classes: set[str] = set()
    for block in re.finditer(r"([^{]+)\{([^}]*)\}", css_text, re.DOTALL):
        selector = block.group(1)
        declaration = block.group(2)
        if _CARD_STYLE_PATTERN.search(declaration):
            for match in re.finditer(r"\.([\w-]+)", selector):
                card_classes.add(match.group(1))
    return frozenset(card_classes)


def _style_tag_css_text(soup: BeautifulSoup) -> str:
    return "".join(style.string or "" for style in soup.find_all("style"))


def _is_flex_container(tag: Tag) -> bool:
    """Return True if the tag is a flex container.

    Detects both inline `display: flex/inline-flex` and class-based rules
    defined in `<style>` tags within the same document.
    """
    styles = _parse_inline_styles(tag.get("style", ""))
    display = styles.get("display", "")
    if display in ("flex", "inline-flex"):
        return True

    flex_classes = _extract_flex_classes(_get_style_tag_css(tag))
    if not flex_classes:
        return False

    tag_classes = tag.get("class", [])
    if isinstance(tag_classes, str):
        tag_classes = tag_classes.split()
    return any(cls in flex_classes for cls in tag_classes)


@lru_cache(maxsize=None)
def _extract_flex_classes(css_text: str) -> frozenset[str]:
    """Scan CSS text for class selectors that set display:flex/inline-flex.

    Note: This scanner is intentionally simple. It does not handle media
    queries, pseudo-classes, nested rules, or external stylesheets.
    """
    flex_classes: set[str] = set()
    for block in re.finditer(r"([^{]+)\{([^}]*)\}", css_text, re.DOTALL):
        selector = block.group(1)
        declaration = block.group(2)
        if re.search(r"\bdisplay\s*:\s*(?:flex|inline-flex)\b", declaration):
            for match in re.finditer(r"\.([\w-]+)", selector):
                flex_classes.add(match.group(1))
    return frozenset(flex_classes)


def _get_style_tag_css(tag: Tag) -> str:
    """Return concatenated text from all <style> tags in the tag's document."""
    root = tag
    while getattr(root, "parent", None) is not None:
        root = root.parent
    if hasattr(root, "find_all"):
        return "".join(s.string or "" for s in root.find_all("style"))
    return ""


def _parse_inline_styles(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for rule in style.split(";"):
        if ":" not in rule:
            continue
        key, value = rule.split(":", 1)
        result[key.strip().lower()] = value.strip()
    return result


def _serialize_inline_styles(styles: dict[str, str]) -> str:
    rules = [f"{k}:{v}" for k, v in styles.items() if v]
    return "; ".join(rules) + ";" if rules else ""


def _merge_classes(existing, new_class: str) -> str:
    if isinstance(existing, list):
        classes = list(existing)
    elif isinstance(existing, str):
        classes = existing.split()
    else:
        classes = []
    if new_class not in classes:
        classes.append(new_class)
    return " ".join(classes)
