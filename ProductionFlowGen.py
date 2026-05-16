import ast
import html
import os
import sys
from pathlib import Path


OUTPUT_NAME = "ProductionFlow.html"
SPRITE_COLUMNS = 20
SPRITE_ROWS = 20
SPRITE_SOURCE = Path("HTML") / "Images" / "Production" / "grid-icon-sheet2.png"
DATABASE_SOURCE = Path("scripts") / "Referance" / "tsn_databases.py"
TARGET_ASSIGNMENTS = {
    "tierCAMC",
    "tier1AMC",
    "tier2AMC",
    "tier3AMC",
    "tierIAMC",
    "tierMAMC",
    "rawMaterials",
    "shipItems",
    "commoditiesDatabase",
    "intelfragmentsDatabase",
    "ordnanceDatabase",
}
TIER_META = {
    "C": {"label": "AMC C", "key": "c", "order": 0},
    "1": {"label": "AMC 1", "key": "1", "order": 1},
    "2": {"label": "AMC 2", "key": "2", "order": 2},
    "3": {"label": "AMC 3", "key": "3", "order": 3},
    "I": {"label": "AMC I", "key": "i", "order": 4},
    "M": {"label": "AMC M", "key": "m", "order": 5},
    "ALL": {"label": "Show All", "key": "all", "order": 6},
}
SPECIAL_VIEW_ITEMS = {"I": set(), "M": set()}
SIGNATURE_COLOURS = {
    "Chemical": "#f0b35e",
    "Cryonic": "#79d8ff",
    "Electro Magnetic": "#7ab3ff",
    "Energy": "#ffd56a",
    "Exotic": "#d186ff",
    "Gravitic": "#94a6ff",
    "Inert Material": "#b4becf",
    "Organic": "#79d58f",
    "Radiological": "#c7ef5d",
    "Shielding": "#63d7cb",
    "Volatile Material": "#ff8f6f",
}


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE = Path(get_base_path())
HTML_DIR = BASE / "HTML"
OUTPUT_PATH = HTML_DIR / OUTPUT_NAME
DATABASE_PATH = BASE / DATABASE_SOURCE
SPRITE_PATH = BASE / SPRITE_SOURCE


def build_sprite_href():
    href = os.path.relpath(SPRITE_PATH, HTML_DIR).replace("\\", "/")
    if SPRITE_PATH.exists():
        stat = SPRITE_PATH.stat()
        href = f"{href}?v={stat.st_mtime_ns}-{stat.st_size}"
    return html.escape(href)


def parse_database_snapshot(path):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    snapshot = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue

        name = node.targets[0].id
        if name not in TARGET_ASSIGNMENTS:
            continue

        try:
            snapshot[name] = ast.literal_eval(node.value)
        except Exception as exc:
            raise ValueError(f"Could not parse {name} from {path}: {exc}") from exc

    missing = sorted(TARGET_ASSIGNMENTS - set(snapshot))
    if missing:
        raise ValueError(f"Missing expected assignments in {path}: {', '.join(missing)}")

    return snapshot


def build_recipe_catalog(snapshot):
    tier_sources = [
        ("C", snapshot["tierCAMC"]),
        ("1", snapshot["tier1AMC"]),
        ("2", snapshot["tier2AMC"]),
        ("3", snapshot["tier3AMC"]),
        ("I", snapshot["tierIAMC"]),
        ("M", snapshot["tierMAMC"]),
    ]

    recipes = {}
    industrial_items = set()
    military_items = set()
    tier_roots = {tier_code: set() for tier_code, _ in tier_sources}

    for tier_code, tier_data in tier_sources:
        for product, ingredients in tier_data.items():
            product_name = str(product).strip()
            ingredient_list = [str(entry).strip() for entry in ingredients]

            record = recipes.setdefault(
                product_name,
                {"ingredients": ingredient_list, "tiers": set()},
            )
            if record["ingredients"] != ingredient_list:
                raise ValueError(f"Conflicting ingredient lists found for {product_name!r}")
            record["tiers"].add(tier_code)
            tier_roots[tier_code].add(product_name)
            if tier_code == "I":
                industrial_items.add(product_name)
            elif tier_code == "M":
                military_items.add(product_name)

    minimum_tier = {}
    for product, data in recipes.items():
        craftable_tiers = [tier for tier in data["tiers"] if tier in TIER_META]
        if craftable_tiers:
            minimum_tier[product] = min(craftable_tiers, key=lambda tier: TIER_META[tier]["order"])

    global SPECIAL_VIEW_ITEMS
    SPECIAL_VIEW_ITEMS = {"I": industrial_items, "M": military_items}

    return recipes, minimum_tier, industrial_items, tier_roots


def build_item_meta(snapshot):
    meta_sources = (
        snapshot["rawMaterials"],
        snapshot["shipItems"],
        snapshot["commoditiesDatabase"],
        snapshot["intelfragmentsDatabase"],
        snapshot["ordnanceDatabase"],
    )

    item_meta = {}
    for source in meta_sources:
        for item, data in source.items():
            if not isinstance(data, dict):
                continue
            item_meta[str(item).strip()] = {
                "icon": data.get("icon"),
                "colour": data.get("colour", "#5f86a8"),
                "size": data.get("size"),
                "signatures": data.get("signatures", data.get("signature")),
            }
    return item_meta


def classify_item(name, minimum_tier, raw_materials):
    if name in raw_materials:
        return {"kind": "raw", "label": "Raw", "filter": "raw", "order": 90}

    tier_code = minimum_tier.get(name)
    if tier_code:
        return {
            "kind": "amc",
            "label": TIER_META[tier_code]["label"],
            "filter": f"tier-{TIER_META[tier_code]['key']}",
            "order": TIER_META[tier_code]["order"],
        }

    return {"kind": "external", "label": "External", "filter": "external", "order": 99}


def collect_subtree_items(root_name, recipes):
    collected = []
    seen = set()

    def walk(item_name):
        if item_name in seen:
            return
        seen.add(item_name)
        collected.append(item_name)
        for ingredient in recipes.get(item_name, {}).get("ingredients", []):
            walk(ingredient)

    walk(root_name)
    return collected


def can_expand_item_for_view(item_name, view_code, minimum_tier, industrial_items):
    if view_code == "ALL":
        return True
    if view_code in SPECIAL_VIEW_ITEMS:
        return item_name in SPECIAL_VIEW_ITEMS[view_code]

    tier_code = minimum_tier.get(item_name)
    if not tier_code:
        return False

    return TIER_META[tier_code]["order"] <= TIER_META[view_code]["order"]


def collect_visible_subtree_items(root_name, recipes, minimum_tier, industrial_items, view_code):
    collected = []
    seen = set()

    def walk(item_name):
        if item_name in seen:
            return
        seen.add(item_name)
        collected.append(item_name)

        if not can_expand_item_for_view(item_name, view_code, minimum_tier, industrial_items):
            return

        for ingredient in recipes.get(item_name, {}).get("ingredients", []):
            walk(ingredient)

    walk(root_name)
    return collected


def collect_external_and_raw_items(roots, recipes, minimum_tier, raw_materials):
    raw_items = set()
    external_items = set()

    for root in roots:
        for item in collect_subtree_items(root, recipes):
            if item in raw_materials:
                raw_items.add(item)
            elif item not in minimum_tier:
                external_items.add(item)

    return raw_items, external_items


def count_descendants(root_name, recipes):
    return max(len(collect_subtree_items(root_name, recipes)) - 1, 0)


def resolve_icon_style(item_name, item_meta):
    meta = item_meta.get(item_name, {})
    icon = meta.get("icon")
    accent = str(meta.get("colour", "#5f86a8"))

    if not isinstance(icon, int) or icon < 0 or icon >= SPRITE_COLUMNS * SPRITE_ROWS:
        return "", accent

    col = icon % SPRITE_COLUMNS
    row = icon // SPRITE_COLUMNS
    style = f' style="--icon-col:{col}; --icon-row:{row}; --item-accent:{html.escape(accent)};"'
    return style, accent


def render_icon(item_name, item_meta, variant="node"):
    icon_style, accent = resolve_icon_style(item_name, item_meta)
    variant_class = "chip" if variant == "chip" else "node"
    if icon_style:
        return (
            f'<span class="node-icon-glow {variant_class}" style="--item-accent:{html.escape(accent)};"></span>'
            f'<span class="node-icon-clip {variant_class}" aria-hidden="true">'
            f'<span class="node-icon sprite {variant_class}"{icon_style}></span>'
            f'</span>'
        )

    fallback = html.escape(item_name[:1].upper() or "?")
    return (
        f'<span class="node-icon fallback {variant_class}" style="--item-accent:{html.escape(accent)};" '
        f'aria-hidden="true">{fallback}</span>'
    )


def format_item_fact_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if isinstance(value, dict):
        return ", ".join(f"{key} {format_item_fact_value(entry)}" for key, entry in value.items())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(format_item_fact_value(entry) for entry in value)
    return str(value)


def normalize_signature_values(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [f"{key} {format_item_fact_value(entry)}" for key, entry in value.items()]
    if isinstance(value, (list, tuple, set)):
        return [format_item_fact_value(entry) for entry in value if format_item_fact_value(entry)]
    return [format_item_fact_value(value)]


def render_node_facts(item_name, item_meta):
    meta = item_meta.get(item_name, {})
    sections = []

    size_value = format_item_fact_value(meta.get("size"))
    if size_value:
        sections.append(
            f'<div class="node-fact-group"><div class="node-facts">'
            f'<span class="node-fact">Size {html.escape(size_value)}</span>'
            f"</div></div>"
        )

    signatures = normalize_signature_values(meta.get("signatures"))
    if signatures:
        signature_tags = []
        for signature in signatures:
            colour = SIGNATURE_COLOURS.get(signature, "#8aa7c4")
            signature_tags.append(
                f'<span class="node-fact signature" style="--signature-colour:{html.escape(colour)};">'
                f"{html.escape(signature)}</span>"
            )
        sections.append(
            '<div class="node-fact-group">'
            '<p class="node-fact-title">Signatures</p>'
            f'<div class="node-facts signature-list">{"".join(signature_tags)}</div>'
            "</div>"
        )

    if not sections:
        return ""

    return f'<div class="node-meta">{"".join(sections)}</div>'


def render_tree_node(
    item_name,
    recipes,
    minimum_tier,
    raw_materials,
    industrial_items,
    item_meta,
    trail,
    view_code,
    depth=0,
):
    classification = classify_item(item_name, minimum_tier, raw_materials)
    child_items = recipes.get(item_name, {}).get("ingredients", [])
    has_children = bool(child_items)
    repeated = item_name in trail
    can_expand_children = has_children and not repeated and can_expand_item_for_view(
        item_name,
        view_code,
        minimum_tier,
        industrial_items,
    )
    hidden_children = has_children and not repeated and not can_expand_children
    node_classes = ["tree-node"]
    use_stack_children = can_expand_children and depth == 1
    use_lateral_children = can_expand_children and depth >= 2
    if use_stack_children:
        node_classes.append("stack-branch")
    if use_lateral_children:
        node_classes.append("lateral")

    body = [f'<div class="{" ".join(node_classes)}">']
    card_markup = render_node_card(
        item_name,
        classification,
        child_items,
        has_children,
        repeated,
        hidden_children,
        industrial_items,
        item_meta,
    )

    if use_lateral_children:
        children_class = "lateral-children multi" if len(child_items) > 1 else "lateral-children single"
        body.append('  <div class="lateral-row">')
        body.append(card_markup)
        body.append(f'    <div class="{children_class}">')
        next_trail = trail | {item_name}
        for child in child_items:
            body.append(
                render_tree_node(
                    child,
                    recipes,
                    minimum_tier,
                    raw_materials,
                    industrial_items,
                    item_meta,
                    next_trail,
                    view_code,
                    depth + 1,
                )
            )
        body.append("    </div>")
        body.append("  </div>")
    else:
        body.append(card_markup)
        if can_expand_children:
            if use_stack_children:
                children_class = "stack-children multi" if len(child_items) > 1 else "stack-children single"
            else:
                children_class = "tree-children multi" if len(child_items) > 1 else "tree-children"
            body.append(f'  <div class="{children_class}">')
            next_trail = trail | {item_name}
            for child in child_items:
                body.append(
                    render_tree_node(
                        child,
                        recipes,
                        minimum_tier,
                        raw_materials,
                        industrial_items,
                        item_meta,
                        next_trail,
                        view_code,
                        depth + 1,
                    )
                )
            body.append("  </div>")

    body.append("</div>")
    return "\n".join(body)


def render_node_card(
    item_name,
    classification,
    child_items,
    has_children,
    repeated,
    hidden_children,
    industrial_items,
    item_meta,
):
    industrial_chip = '<span class="node-chip industrial">IAMC</span>' if item_name in industrial_items else ""
    signature_tokens = [
        build_dom_token(signature)
        for signature in normalize_signature_values(item_meta.get(item_name, {}).get("signatures"))
    ]
    signature_attr = f' data-signature-keys="|{"|".join(signature_tokens)}|"' if signature_tokens else ""

    body = [
        f'  <div class="node-card {classification["kind"]}"{signature_attr}>',
        '    <div class="node-media">',
        f"      {render_icon(item_name, item_meta, 'node')}",
        "    </div>",
        '    <div class="node-body">',
        '      <div class="node-topline">',
        f'        <span class="node-chip badge {classification["kind"]}">{html.escape(classification["label"])}</span>',
        f"        {industrial_chip}",
        "      </div>",
        f'      <h3 class="node-title">{html.escape(item_name)}</h3>',
    ]

    facts_markup = render_node_facts(item_name, item_meta)
    if facts_markup:
        body.append(f"      {facts_markup}")

    if repeated:
        body.append('      <p class="node-note">Already expanded higher in this chain.</p>')
    elif hidden_children:
        count = len(child_items)
        body.append(
            f'      <p class="node-note">{count} input{"s" if count != 1 else ""} hidden in this view.</p>'
        )
    elif classification["kind"] == "raw":
        body.append('      <p class="node-note">Source material gathered directly.</p>')
    elif classification["kind"] == "external":
        body.append('      <p class="node-note">Supplied by another chain not covered here.</p>')
    elif not has_children:
        body.append('      <p class="node-note">No ingredient data found.</p>')
    else:
        count = len(child_items)
        body.append(f'      <p class="node-note">{count} input{"s" if count != 1 else ""}.</p>')

    body.extend(["    </div>", "  </div>"])
    return "\n".join(body)


def render_reference_chips(items, minimum_tier, raw_materials, item_meta):
    chips = []
    for item in items:
        classification = classify_item(item, minimum_tier, raw_materials)
        chips.append(
            f"""
        <div class="reference-chip {classification['kind']}">
          <span class="chip-icon-wrap">{render_icon(item, item_meta, 'chip')}</span>
          <span class="chip-label">{html.escape(item)}</span>
          <span class="chip-badge {classification['kind']}">{html.escape(classification['label'])}</span>
        </div>"""
        )
    return "".join(chips)


def build_recipe_cards(roots, recipes, minimum_tier, raw_materials, industrial_items, item_meta):
    cards = []

    for root in roots:
        subtree_items = collect_subtree_items(root, recipes)
        direct_inputs = recipes[root]["ingredients"]
        external_count = sum(
            1 for item in subtree_items if item not in minimum_tier and item not in raw_materials
        )
        raw_count = sum(1 for item in subtree_items if item in raw_materials)
        minimum_label = classify_item(root, minimum_tier, raw_materials)["label"]
        industrial_flag = "true" if root in industrial_items else "false"
        search_blob = " ".join(subtree_items).casefold()
        tier_filter = classify_item(root, minimum_tier, raw_materials)["filter"]
        node_count = count_descendants(root, recipes)

        cards.append(
            f"""
      <article class="recipe-card"
        data-tier="{html.escape(tier_filter)}"
        data-industrial="{industrial_flag}"
        data-search="{html.escape(search_blob)}">
        <header class="recipe-header">
          <div>
            <p class="eyebrow">{html.escape(minimum_label)} workflow</p>
            <h2>{html.escape(root)}</h2>
          </div>
          <div class="recipe-badges">
            <span class="summary-pill">{len(direct_inputs)} direct input{"s" if len(direct_inputs) != 1 else ""}</span>
            <span class="summary-pill">{node_count} downstream node{"s" if node_count != 1 else ""}</span>
            <span class="summary-pill">{raw_count} raw</span>
            <span class="summary-pill">{external_count} external</span>
            {'<span class="summary-pill industrial">IAMC</span>' if root in industrial_items else ''}
          </div>
        </header>
        <div class="chart-shell">
          <div class="tree-canvas">
{render_tree_node(root, recipes, minimum_tier, raw_materials, industrial_items, item_meta, set(), "ALL")}
          </div>
        </div>
      </article>"""
        )

    return "".join(cards)


def build_tier_buttons(tier_codes):
    buttons = []
    for index, tier_code in enumerate(tier_codes):
        meta = TIER_META[tier_code]
        active = "true" if index == 0 else "false"
        selected_class = " is-selected" if index == 0 else ""
        buttons.append(
            f'<button class="tier-tab{selected_class}" type="button" data-tier-tab="{meta["key"]}" '
            f'aria-selected="{active}">{html.escape(meta["label"])}</button>'
        )
    return "".join(buttons)


def build_dom_token(value):
    token = []
    for char in str(value).strip().casefold():
        if char.isalnum():
            token.append(char)
        else:
            token.append("-")
    compact = "".join(token).strip("-")
    while "--" in compact:
        compact = compact.replace("--", "-")
    return compact or "item"


def get_signature_sort_key(signature):
    known = list(SIGNATURE_COLOURS)
    if signature in SIGNATURE_COLOURS:
        return (0, known.index(signature), signature.casefold())
    return (1, 999, signature.casefold())


def collect_signature_matches_for_view(
    roots,
    recipes,
    minimum_tier,
    industrial_items,
    item_meta,
    view_code,
):
    signature_map = {}

    for root in roots:
        for item in collect_visible_subtree_items(root, recipes, minimum_tier, industrial_items, view_code):
            signatures = normalize_signature_values(item_meta.get(item, {}).get("signatures"))
            if not signatures:
                continue

            for signature in signatures:
                items = signature_map.setdefault(signature, {})
                entry = items.setdefault(item, {"roots": set()})
                entry["roots"].add(root)

    return signature_map


def build_signature_match_card(
    item_name,
    roots,
    focus_root,
    tier_key,
    minimum_tier,
    raw_materials,
    industrial_items,
    item_meta,
):
    classification = classify_item(item_name, minimum_tier, raw_materials)
    meta = item_meta.get(item_name, {})
    signature_tokens = [
        build_dom_token(signature)
        for signature in normalize_signature_values(meta.get("signatures"))
    ]
    signature_attr = f' data-signature-keys="|{"|".join(signature_tokens)}|"' if signature_tokens else ""
    size_value = format_item_fact_value(meta.get("size"))
    fact_tags = []
    if size_value:
        fact_tags.append(f'<span class="node-fact">Size {html.escape(size_value)}</span>')

    for signature in normalize_signature_values(meta.get("signatures")):
        colour = SIGNATURE_COLOURS.get(signature, "#8aa7c4")
        fact_tags.append(
            f'<span class="node-fact signature" style="--signature-colour:{html.escape(colour)};">'
            f"{html.escape(signature)}</span>"
        )

    industrial_chip = '<span class="node-chip industrial">IAMC</span>' if item_name in industrial_items else ""
    root_count_label = f'{len(roots)} schematic{"s" if len(roots) != 1 else ""}'
    root_label = html.escape(", ".join(roots))
    title = f"Linked schematics: {', '.join(roots)}"

    return (
        f'<button class="signature-match-card {classification["kind"]}" type="button" '
        f'data-result-tier="{tier_key}" data-result-root="{build_dom_token(focus_root)}" '
        f"{signature_attr} "
        f'title="{html.escape(title)}">'
        f'<span class="signature-match-media">{render_icon(item_name, item_meta, "node")}</span>'
        f'<span class="signature-match-body">'
        f'<span class="signature-match-topline">'
        f'<span class="node-chip badge {classification["kind"]}">{html.escape(classification["label"])}</span>'
        f"{industrial_chip}"
        f'<span class="signature-result-count">{root_count_label}</span>'
        f"</span>"
        f'<span class="signature-match-title">{html.escape(item_name)}</span>'
        f'<span class="signature-match-facts">{"".join(fact_tags)}</span>'
        f'<span class="signature-match-note">Linked schematics: {root_label}</span>'
        f"</span>"
        f"</button>"
    )


def build_signature_lookup(
    tier_code,
    ordered_roots,
    recipes,
    minimum_tier,
    raw_materials,
    industrial_items,
    item_meta,
):
    signature_map = collect_signature_matches_for_view(
        ordered_roots,
        recipes,
        minimum_tier,
        industrial_items,
        item_meta,
        tier_code,
    )
    if not signature_map:
        return ""

    signature_buttons = []
    aggregated_items = {}
    tier_key = TIER_META[tier_code]["key"]
    tier_label = "All Tiers" if tier_code == "ALL" else TIER_META[tier_code]["label"]
    panel_note = (
        "Choose one or more signatures from the full dataset. Each additional signature narrows the list to items that match every selected signature."
        if tier_code == "ALL"
        else "Choose one or more signatures for the active tier. Each additional signature narrows the list to items that match every selected signature."
    )

    for signature in sorted(signature_map, key=get_signature_sort_key):
        items = signature_map[signature]
        signature_token = build_dom_token(signature)
        colour = SIGNATURE_COLOURS.get(signature, "#8aa7c4")
        signature_buttons.append(
            f'<button class="signature-filter" type="button" '
            f'data-signature-tier="{tier_key}" data-signature="{signature_token}" '
            f'data-signature-name="{html.escape(signature)}" '
            f'style="--signature-colour:{html.escape(colour)};">'
            f'<span>{html.escape(signature)}</span><span class="signature-filter-count">{len(items)}</span>'
            f"</button>"
        )

        for item_name, entry in items.items():
            aggregate = aggregated_items.setdefault(item_name, {"roots": set()})
            aggregate["roots"].update(entry["roots"])

    result_items = []
    for item in sorted(
        aggregated_items,
        key=lambda value: (
            classify_item(value, minimum_tier, raw_materials)["order"],
            value.casefold(),
        ),
    ):
        roots = sorted(aggregated_items[item]["roots"], key=str.casefold)
        focus_root = item if item in ordered_roots else roots[0]
        result_items.append(
            build_signature_match_card(
                item,
                roots,
                focus_root,
                tier_key,
                minimum_tier,
                raw_materials,
                industrial_items,
                item_meta,
            )
        )

    return (
        f'<section class="signature-lookup" data-signature-lookup="{tier_key}" '
        f'data-signature-panel="{tier_key}" data-signature-label="{html.escape(tier_label)}" '
        f'{"hidden" if tier_code not in ("C", "ALL") else ""}>'
        f'<p class="signature-panel-note">{html.escape(panel_note)}</p>'
        f'<div class="signature-filter-row">{"".join(signature_buttons)}</div>'
        f'<div class="signature-active-filters" data-signature-active="{tier_key}" hidden>'
        f'<span class="signature-active-label">Filter Lock</span>'
        f'<div class="signature-active-list" data-signature-active-list="{tier_key}"></div>'
        f"</div>"
        f'<div class="signature-results" data-signature-results="{tier_key}" hidden>'
        f'<p class="signature-results-empty" data-signature-empty="{tier_key}">Select one or more signature channels to query the archive.</p>'
        f'<div class="signature-result-group" data-signature-group="{tier_key}">{"".join(result_items)}</div>'
        f"</div>"
        f"</section>"
    )


def get_display_roots_for_tier(tier_code, tier_roots):
    if tier_code == "C":
        included = ["C"]
    elif tier_code == "1":
        included = ["C", "1"]
    elif tier_code == "2":
        included = ["C", "1", "2"]
    elif tier_code == "3":
        included = ["C", "1", "2", "3"]
    elif tier_code == "M":
        included = ["M"]
    elif tier_code == "ALL":
        included = ["C", "1", "2", "3", "I", "M"]
    else:
        included = ["I"]

    roots = set()
    for code in included:
        roots.update(tier_roots.get(code, set()))
    return roots


def build_root_selector(tier_code, ordered_roots):
    selector_items = []
    for index, root in enumerate(ordered_roots):
        selected_class = " is-selected" if index == 0 else ""
        root_token = build_dom_token(root)
        selector_items.append(
            f'<button class="root-tag{selected_class}" type="button" '
            f'data-focus-tier="{TIER_META[tier_code]["key"]}" '
            f'data-focus-root="{root_token}">{html.escape(root)}</button>'
        )
    return "".join(selector_items)


def build_signature_explorer(tier_roots, recipes, minimum_tier, raw_materials, industrial_items, item_meta):
    tier_code = "ALL"
    roots = get_display_roots_for_tier(tier_code, tier_roots)
    ordered_roots = sorted(
        roots,
        key=lambda item: (
            classify_item(item, minimum_tier, raw_materials)["order"],
            item.casefold(),
        ),
    )
    panel = build_signature_lookup(
        tier_code,
        ordered_roots,
        recipes,
        minimum_tier,
        raw_materials,
        industrial_items,
        item_meta,
    )

    return f"""
    <section class="signature-explorer">
      <div class="signature-explorer-header">
        <div>
          <p class="eyebrow">Signature Index</p>
          <h2>Cross-Signature Query</h2>
          <p class="signature-explorer-copy">Query the full manufacturing archive by one or more signature channels, then review each matching item as a terminal card with icon, size, linked schematics, and companion signatures.</p>
        </div>
        <div class="signature-explorer-status" data-signature-status>Archive scope: All Tiers</div>
      </div>
      {panel}
    </section>"""


def build_tier_panel(tier_code, roots, recipes, minimum_tier, raw_materials, industrial_items, item_meta):
    meta = TIER_META[tier_code]
    ordered_roots = sorted(
        roots,
        key=lambda item: (
            classify_item(item, minimum_tier, raw_materials)["order"],
            item.casefold(),
        ),
    )

    columns = []
    for root in ordered_roots:
        root_token = build_dom_token(root)
        subtree_items = collect_visible_subtree_items(
            root,
            recipes,
            minimum_tier,
            industrial_items,
            tier_code,
        )
        raw_count = sum(1 for item in subtree_items if item in raw_materials)
        external_count = sum(1 for item in subtree_items if item not in minimum_tier and item not in raw_materials)
        node_count = max(len(subtree_items) - 1, 0)
        columns.append(
            f"""
            <section class="workflow-column" id="workflow-{meta['key']}-{root_token}" data-workflow-root="{root_token}">
              <header class="workflow-header">
                <p class="workflow-eyebrow">{html.escape(meta['label'])} Schematic</p>
                <h2>{html.escape(root)}</h2>
                <div class="workflow-stats">
                  <span class="summary-pill">{node_count} node{"s" if node_count != 1 else ""}</span>
                  <span class="summary-pill">{raw_count} raw</span>
                  <span class="summary-pill">{external_count} external</span>
                </div>
              </header>
              <div class="workflow-tree">
{render_tree_node(root, recipes, minimum_tier, raw_materials, industrial_items, item_meta, set(), tier_code)}
              </div>
            </section>"""
        )

    return f"""
      <section class="tier-panel" data-tier-panel="{meta['key']}" {'hidden' if tier_code != 'C' else ''}>
        <div class="tier-panel-header">
          <div>
            <p class="eyebrow">{html.escape(meta['label'])} Channel</p>
            <h2>{len(ordered_roots)} production schematic{"s" if len(ordered_roots) != 1 else ""}</h2>
            <p class="tier-panel-copy">Load an output tag to recenter the board, then pan across every dependency cleared for this AMC channel.</p>
          </div>
          <div class="view-controls">
            <button class="nav-link zoom-button" type="button" data-zoom-tier="{meta['key']}" data-zoom-direction="out">Scale -</button>
            <button class="nav-link zoom-button" type="button" data-zoom-tier="{meta['key']}" data-zoom-direction="in">Scale +</button>
            <button class="nav-link reset-view-button" type="button" data-reset-tier="{meta['key']}">Recenter</button>
          </div>
        </div>
        <div class="root-selector" data-root-selector="{meta['key']}">
          {build_root_selector(tier_code, ordered_roots)}
        </div>
        <div class="tree-viewport" data-pan-viewport="{meta['key']}">
          <div class="tree-surface" data-pan-surface="{meta['key']}">
{''.join(columns)}
          </div>
        </div>
      </section>"""


def build_page(recipes, minimum_tier, raw_materials, industrial_items, item_meta):
    roots = sorted(
        recipes,
        key=lambda item: (
            classify_item(item, minimum_tier, raw_materials)["order"],
            item.casefold(),
        ),
    )
    all_items = sorted({item for root in roots for item in collect_subtree_items(root, recipes)})
    raw_items, external_items = collect_external_and_raw_items(roots, recipes, minimum_tier, raw_materials)
    recipe_cards = build_recipe_cards(
        roots,
        recipes,
        minimum_tier,
        raw_materials,
        industrial_items,
        item_meta,
    )
    sprite_href = build_sprite_href()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Production Flow</title>
  <style>
    :root {{
      --bg: #051019;
      --panel: rgba(7, 18, 29, 0.88);
      --card: rgba(12, 24, 37, 0.96);
      --line: rgba(116, 178, 234, 0.2);
      --line-strong: rgba(116, 178, 234, 0.4);
      --text: #e9f5ff;
      --muted: #9eb3c8;
      --accent: #8cd3ff;
      --amc-c: #4fc7c4;
      --amc-1: #67d57d;
      --amc-2: #f4bb61;
      --amc-3: #ef8f65;
      --raw: #63b8ff;
      --external: #7b8596;
      --industrial: #d869c6;
      --shadow: 0 20px 55px rgba(0, 0, 0, 0.38);
      --radius: 24px;
      --sprite-size: 38px;
      --sprite-sheet-size: calc(var(--sprite-size) * {SPRITE_COLUMNS});
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: "Trebuchet MS", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top, rgba(58, 139, 211, 0.22), transparent 30%),
        linear-gradient(180deg, rgba(3, 9, 16, 0.68), rgba(3, 9, 16, 0.95)),
        url("Images/starfield.jpg") center/cover fixed;
    }}
    .page {{ width: min(1680px, calc(100vw - 28px)); margin: 18px auto 40px; }}
    .hero {{
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 30px;
      background: linear-gradient(180deg, rgba(8, 21, 34, 0.97), rgba(8, 17, 30, 0.82));
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .hero-top {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }}
    .hero h1 {{ margin: 0; font-size: clamp(2rem, 4vw, 3.45rem); letter-spacing: 0.03em; }}
    .hero p {{ margin: 10px 0 0; max-width: 72rem; color: var(--muted); line-height: 1.55; }}
    .nav-group {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }}
    .nav-link {{
      display: inline-flex; align-items: center; justify-content: center; min-width: 164px;
      padding: 12px 18px; border: 1px solid var(--line-strong); border-radius: 999px;
      text-decoration: none; color: var(--text); background: rgba(18, 35, 58, 0.9);
    }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 22px; }}
    .summary-box {{ padding: 16px 18px; border: 1px solid var(--line); border-radius: 18px; background: rgba(10, 24, 38, 0.76); }}
    .summary-box strong {{ display: block; font-size: 1.6rem; margin-bottom: 4px; }}
    .summary-box span {{ color: var(--muted); font-size: 0.93rem; }}
    .legend-row, .filters, .reference-section, .recipes {{ margin-top: 18px; }}
    .legend-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .legend-pill, .summary-pill, .node-chip, .chip-badge {{
      display: inline-flex; align-items: center; gap: 7px; min-height: 32px; padding: 6px 11px;
      border-radius: 999px; border: 1px solid rgba(255, 255, 255, 0.09); font-size: 0.88rem;
      line-height: 1.2; white-space: nowrap;
    }}
    .legend-pill::before {{
      content: ""; width: 10px; height: 10px; border-radius: 999px; background: currentColor;
      box-shadow: 0 0 14px currentColor;
    }}
    .legend-pill.amc-c {{ color: var(--amc-c); background: rgba(43, 89, 88, 0.3); }}
    .legend-pill.amc-1 {{ color: var(--amc-1); background: rgba(47, 83, 46, 0.28); }}
    .legend-pill.amc-2 {{ color: var(--amc-2); background: rgba(94, 68, 24, 0.32); }}
    .legend-pill.amc-3 {{ color: var(--amc-3); background: rgba(92, 47, 26, 0.34); }}
    .legend-pill.raw, .badge.raw, .chip-badge.raw {{ color: var(--raw); background: rgba(37, 69, 104, 0.42); }}
    .legend-pill.external, .badge.external, .chip-badge.external {{ color: #edf2fa; background: rgba(64, 71, 85, 0.44); }}
    .legend-pill.industrial, .industrial, .node-chip.industrial {{ color: var(--industrial); background: rgba(95, 31, 82, 0.34); }}
    .badge.amc {{ color: #effff6; background: rgba(47, 83, 46, 0.4); }}
    .filters {{ display: grid; grid-template-columns: minmax(260px, 2fr) minmax(180px, 1fr) auto; gap: 12px; align-items: end; }}
    .filter-group {{ display: flex; flex-direction: column; gap: 6px; }}
    .filter-group label {{ color: var(--muted); font-size: 0.92rem; letter-spacing: 0.04em; text-transform: uppercase; }}
    .filter-group input, .filter-group select {{
      width: 100%; padding: 14px 16px; border: 1px solid var(--line); border-radius: 14px;
      color: var(--text); background: rgba(10, 21, 36, 0.92); outline: none;
    }}
    .toggle-wrap {{
      display: flex; align-items: center; gap: 10px; min-height: 48px; padding: 0 14px;
      border: 1px solid var(--line); border-radius: 14px; background: rgba(10, 21, 36, 0.92);
    }}
    .toggle-wrap label {{ color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.9rem; }}
    .results-bar {{ display: flex; justify-content: space-between; gap: 14px; align-items: center; margin-top: 14px; color: var(--muted); }}
    .reference-section {{
      padding: 18px; border: 1px solid var(--line); border-radius: var(--radius);
      background: rgba(9, 20, 32, 0.78); box-shadow: var(--shadow);
    }}
    .reference-section h2, .recipes-title {{ margin: 0 0 12px; font-size: 1.25rem; letter-spacing: 0.03em; }}
    .reference-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    .reference-chip {{
      display: flex; align-items: center; gap: 12px; min-width: 0; padding: 12px 14px;
      border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; background: rgba(12, 24, 37, 0.86);
    }}
    .chip-icon-wrap {{ position: relative; display: inline-flex; width: 40px; min-width: 40px; height: 40px; align-items: center; justify-content: center; }}
    .chip-label {{ min-width: 0; flex: 1; font-weight: 700; }}
    .recipes {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(540px, 1fr)); gap: 18px; }}
    .recipe-card {{
      padding: 20px; border: 1px solid var(--line); border-radius: var(--radius);
      background: var(--card); box-shadow: var(--shadow); overflow: hidden;
    }}
    .recipe-header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }}
    .eyebrow {{ margin: 0 0 8px; color: var(--accent); font-size: 0.82rem; letter-spacing: 0.13em; text-transform: uppercase; }}
    .recipe-header h2 {{ margin: 0; font-size: 1.65rem; line-height: 1.1; }}
    .recipe-badges {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    .summary-pill {{ color: #d7ebff; background: rgba(24, 43, 67, 0.88); }}
    .chart-shell {{ overflow: auto; padding-bottom: 6px; }}
    .tree-canvas {{ width: max-content; min-width: 100%; padding: 6px 12px 18px; }}
    .tree-node {{ position: relative; display: flex; flex-direction: column; align-items: center; min-width: 180px; }}
    .node-card {{
      position: relative; display: grid; grid-template-columns: 56px minmax(0, 1fr); gap: 12px;
      width: 100%; max-width: 270px; padding: 12px; border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: linear-gradient(180deg, rgba(13, 24, 39, 0.98), rgba(9, 18, 29, 0.98));
      box-shadow: 0 12px 26px rgba(0, 0, 0, 0.28);
    }}
    .node-card::before {{
      content: ""; position: absolute; inset: 0 auto 0 0; width: 4px;
      border-radius: 18px 0 0 18px; background: var(--line-strong);
    }}
    .node-card.amc::before {{ background: linear-gradient(180deg, var(--amc-c), var(--amc-3)); }}
    .node-card.raw::before {{ background: var(--raw); }}
    .node-card.external::before {{ background: var(--external); }}
    .node-media {{ position: relative; display: flex; align-items: center; justify-content: center; min-height: 56px; }}
    .node-icon, .node-icon-glow {{ position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 14px; }}
    .node-icon-glow {{
      background: radial-gradient(circle, color-mix(in srgb, var(--item-accent), transparent 72%), transparent 72%);
      filter: blur(8px); opacity: 0.9; transform: scale(0.92);
    }}
    .node-icon.sprite {{
      width: 100%; height: 100%; background-image: url("{sprite_href}"); background-repeat: no-repeat;
      background-size: var(--sprite-sheet-size) var(--sprite-sheet-size);
      background-position: calc(var(--icon-col) * var(--sprite-size) * -1) calc(var(--icon-row) * var(--sprite-size) * -1);
      border: 1px solid rgba(255, 255, 255, 0.08); background-color: rgba(8, 14, 22, 0.88);
    }}
    .node-icon.fallback {{
      display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.1rem;
      background: color-mix(in srgb, var(--item-accent), #0f1c29 48%); color: #eef7ff;
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .node-body {{ min-width: 0; }}
    .node-topline {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }}
    .node-title {{ margin: 0; font-size: 1.02rem; line-height: 1.2; }}
    .node-note {{ margin: 6px 0 0; color: var(--muted); font-size: 0.85rem; line-height: 1.35; }}
    .tree-children {{
      position: relative; display: flex; justify-content: center; gap: 14px; margin-top: 18px; padding-top: 24px;
      isolation: isolate;
    }}
    .tree-children::before {{
      content: ""; position: absolute; top: 0; left: 50%; width: 2px; height: 14px;
      transform: translateX(-50%); background: var(--line-strong); z-index: 2; pointer-events: none;
    }}
    .tree-children.multi::after {{
      content: ""; position: absolute; top: 14px; left: 18px; right: 18px; height: 2px; background: var(--line-strong);
      z-index: 2; pointer-events: none;
    }}
    .tree-children > .tree-node {{
      z-index: 1;
    }}
    .tree-children > .tree-node::before {{
      content: ""; position: absolute; top: -24px; left: 50%; width: 2px; height: 24px;
      transform: translateX(-50%); background: var(--line-strong); z-index: 2; pointer-events: none;
    }}
    .empty-state {{
      display: none; padding: 24px; border: 1px dashed var(--line-strong); border-radius: var(--radius);
      color: var(--muted); text-align: center; background: rgba(8, 17, 30, 0.74);
    }}
    @media (max-width: 1120px) {{
      .filters {{ grid-template-columns: 1fr 1fr; }}
      .toggle-wrap {{ grid-column: 1 / -1; justify-content: flex-start; }}
      .recipes {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 760px) {{
      .page {{ width: min(100vw - 14px, 1680px); margin-top: 8px; }}
      .hero {{ padding: 18px; }}
      .hero-top, .recipe-header {{ flex-direction: column; }}
      .nav-group {{ justify-content: flex-start; }}
      .filters {{ grid-template-columns: 1fr; }}
      .results-bar {{ flex-direction: column; align-items: flex-start; }}
      .reference-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-top">
        <div>
          <h1>Production Flow</h1>
          <p>
            AMC production trees generated directly from <code>scripts/Referance/tsn_databases.py</code>.
            Each node shows the minimum AMC tier that can manufacture it, marks raw resources, and flags anything supplied by another chain not modelled here.
          </p>
          <p>
            Icons are pulled from <code>grid-icon-sheet2.png</code> using the database icon indices.
          </p>
        </div>
        <div class="nav-group">
          <a class="nav-link" href="index.html">Back to System Map</a>
          <a class="nav-link" href="Library.html">Open Ship Library</a>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-box"><strong>{len(roots)}</strong><span>Craftable outputs</span></div>
        <div class="summary-box"><strong>{len(raw_items)}</strong><span>Raw resources in chain</span></div>
        <div class="summary-box"><strong>{len(external_items)}</strong><span>External dependencies</span></div>
        <div class="summary-box"><strong>{len(industrial_items)}</strong><span>Also valid in IAMC</span></div>
        <div class="summary-box"><strong>{len(all_items)}</strong><span>Total unique nodes</span></div>
      </div>

      <div class="legend-row">
        <span class="legend-pill amc-c">AMC C</span>
        <span class="legend-pill amc-1">AMC 1</span>
        <span class="legend-pill amc-2">AMC 2</span>
        <span class="legend-pill amc-3">AMC 3</span>
        <span class="legend-pill raw">Raw Resource</span>
        <span class="legend-pill external">External Chain</span>
        <span class="legend-pill industrial">Also in IAMC</span>
      </div>
      <div class="filters">
        <div class="filter-group">
          <label for="search-input">Search</label>
          <input id="search-input" type="search" placeholder="Item name or dependency..." />
        </div>
        <div class="filter-group">
          <label for="tier-filter">Minimum Tier</label>
          <select id="tier-filter">
            <option value="all">All tiers</option>
            <option value="tier-c">AMC C</option>
            <option value="tier-1">AMC 1</option>
            <option value="tier-2">AMC 2</option>
            <option value="tier-3">AMC 3</option>
          </select>
        </div>
        <div class="toggle-wrap">
          <input id="industrial-only" type="checkbox" />
          <label for="industrial-only">IAMC capable only</label>
        </div>
      </div>

      <div class="results-bar">
        <div id="results-count">Showing {len(roots)} of {len(roots)} recipes</div>
        <div id="active-filter-label">All tiers</div>
      </div>
    </section>

    <section class="reference-section">
      <h2>External Inputs</h2>
      <div class="reference-grid">
{render_reference_chips(sorted(external_items), minimum_tier, raw_materials, item_meta)}
      </div>
    </section>

    <section class="reference-section">
      <h2>Raw Materials</h2>
      <div class="reference-grid">
{render_reference_chips(sorted(raw_items), minimum_tier, raw_materials, item_meta)}
      </div>
    </section>

    <section class="reference-section">
      <h2 class="recipes-title">Recipe Trees</h2>
      <div class="recipes" id="recipe-grid">
{recipe_cards}
      </div>
    </section>

    <section class="empty-state" id="empty-state">
      No recipe trees match the current filter selection.
    </section>
  </main>

  <script>
    const cards = Array.from(document.querySelectorAll('.recipe-card'));
    const searchInput = document.getElementById('search-input');
    const tierFilter = document.getElementById('tier-filter');
    const industrialOnly = document.getElementById('industrial-only');
    const resultsCount = document.getElementById('results-count');
    const activeFilterLabel = document.getElementById('active-filter-label');
    const emptyState = document.getElementById('empty-state');

    function applyFilters() {{
      const term = searchInput.value.trim().toLowerCase();
      const selectedTier = tierFilter.value;
      const requireIndustrial = industrialOnly.checked;
      let visibleCount = 0;

      cards.forEach((card) => {{
        const tierMatch = selectedTier === 'all' || card.dataset.tier === selectedTier;
        const industrialMatch = !requireIndustrial || card.dataset.industrial === 'true';
        const searchMatch = !term || card.dataset.search.includes(term);
        const visible = tierMatch && industrialMatch && searchMatch;
        card.style.display = visible ? '' : 'none';
        if (visible) {{
          visibleCount += 1;
        }}
      }});

      resultsCount.textContent = `Showing ${{visibleCount}} of ${{cards.length}} recipes`;
      const tierLabel = selectedTier === 'all'
        ? 'All tiers'
        : tierFilter.options[tierFilter.selectedIndex].textContent;
      activeFilterLabel.textContent = requireIndustrial ? `${{tierLabel}}, IAMC capable` : tierLabel;
      emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
    }}

    searchInput.addEventListener('input', applyFilters);
    tierFilter.addEventListener('change', applyFilters);
    industrialOnly.addEventListener('change', applyFilters);
    applyFilters();
  </script>
</body>
</html>"""


def build_page(recipes, minimum_tier, raw_materials, industrial_items, item_meta, tier_roots):
    tier_codes = ["C", "1", "2", "3", "I", "M", "ALL"]
    all_roots = sorted({item for tier_code in ("C", "1", "2", "3", "I", "M") for item in tier_roots.get(tier_code, set())})
    all_items = sorted({item for root in all_roots for item in collect_subtree_items(root, recipes)})
    raw_items, external_items = collect_external_and_raw_items(all_roots, recipes, minimum_tier, raw_materials)
    sprite_href = build_sprite_href()
    tab_buttons = build_tier_buttons(tier_codes)
    signature_explorer = build_signature_explorer(
        tier_roots,
        recipes,
        minimum_tier,
        raw_materials,
        industrial_items,
        item_meta,
    )
    tab_panels = "".join(
        build_tier_panel(
            tier_code,
            get_display_roots_for_tier(tier_code, tier_roots),
            recipes,
            minimum_tier,
            raw_materials,
            industrial_items,
            item_meta,
        )
        for tier_code in tier_codes
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Manufacturing Data Terminal</title>
  <style>
    :root {{--bg:#061311;--line:rgba(96,214,192,.2);--line-strong:rgba(106,236,212,.42);--line-bright:rgba(146,255,232,.78);--text:#e5fff6;--muted:#8db4ab;--accent:#93ffd7;--accent-warm:#ffc66d;--amc-c:#4fd9bb;--amc-1:#b9ef77;--amc-2:#ffd368;--amc-3:#ff9f6d;--amc-i:#ff758f;--amc-m:#ff5f5f;--raw:#82cfff;--external:#8a96a4;--shadow:0 24px 64px rgba(0,0,0,.44),inset 0 1px 0 rgba(184,255,241,.04);--radius:24px;--sprite-size:64px;--sprite-sheet-size:calc(var(--sprite-size) * {SPRITE_COLUMNS});}}
    * {{box-sizing:border-box;}}
    html {{color-scheme:dark;}}
    [hidden] {{display:none !important;}}
    body {{margin:0;min-height:100vh;color:var(--text);font-family:"Bahnschrift","Segoe UI",sans-serif;background:radial-gradient(circle at 14% 12%,rgba(147,255,215,.16),transparent 20%),radial-gradient(circle at 88% 9%,rgba(255,198,109,.1),transparent 18%),linear-gradient(180deg,rgba(4,13,12,.98),rgba(3,9,11,1));}}
    body::before {{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(rgba(147,255,215,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(147,255,215,.05) 1px,transparent 1px);background-size:36px 36px;opacity:.34;mix-blend-mode:screen;}}
    body::after {{content:"";position:fixed;inset:0;pointer-events:none;background:repeating-linear-gradient(180deg,rgba(255,255,255,.03) 0 1px,transparent 1px 4px);opacity:.08;}}
    .page {{position:relative;width:min(100vw - 18px,1880px);margin:10px auto 22px;}}
    .hero,.signature-explorer,.tab-shell {{position:relative;overflow:hidden;border:1px solid var(--line);box-shadow:var(--shadow);backdrop-filter:blur(12px);}}
    .hero::before,.signature-explorer::before,.tab-shell::before {{content:"";position:absolute;inset:0 0 auto 0;height:2px;background:linear-gradient(90deg,transparent,var(--line-bright),transparent);opacity:.88;}}
    .hero {{padding:24px;border-radius:26px;background:linear-gradient(180deg,rgba(8,24,21,.96),rgba(5,14,15,.94));}}
    .hero-top,.tier-panel-header {{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;}}
    .hero-copy {{max-width:78rem;}}
    .hero h1 {{margin:0;font-size:clamp(1.8rem,3.8vw,3.15rem);letter-spacing:.08em;text-transform:uppercase;font-family:"Consolas","Lucida Console",monospace;text-shadow:0 0 18px rgba(147,255,215,.16);}}
    .hero p {{margin:8px 0 0;max-width:72rem;color:var(--muted);line-height:1.45;}}
    .hero-side {{display:grid;gap:12px;justify-items:end;min-width:290px;}}
    .terminal-status {{display:grid;gap:8px;min-width:min(100%,320px);padding:14px 16px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,rgba(8,22,20,.92),rgba(5,14,15,.84));}}
    .terminal-id {{display:block;color:var(--accent);font-family:"Consolas","Lucida Console",monospace;font-size:.82rem;letter-spacing:.18em;text-transform:uppercase;}}
    .terminal-status-row {{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;}}
    .terminal-status-pill {{display:inline-flex;align-items:center;min-height:28px;padding:5px 9px;border:1px solid rgba(255,255,255,.08);border-radius:999px;background:rgba(13,34,29,.86);color:#dcfff4;font-family:"Consolas","Lucida Console",monospace;font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;}}
    .page-nav-stack {{display:grid;gap:8px;width:min(100%,280px);}}
    .legend-row,.tier-tabs,.workflow-stats {{display:flex;gap:10px;flex-wrap:wrap;}}
    .nav-link,.tier-tab,.summary-pill,.node-chip,.root-tag,.legend-pill,.signature-filter,.signature-explorer-status,.signature-active-chip,.signature-result-count,.node-fact,.node-fact-title {{font-family:"Consolas","Lucida Console",monospace;}}
    .nav-link,.tier-tab,.summary-pill,.node-chip {{display:inline-flex;align-items:center;justify-content:center;min-height:32px;padding:6px 11px;border:1px solid rgba(255,255,255,.09);border-radius:999px;color:var(--text);text-decoration:none;background:rgba(12,29,25,.92);}}
    .nav-link {{min-width:164px;padding:12px 18px;border-color:var(--line-strong);letter-spacing:.08em;text-transform:uppercase;font-size:.82rem;}}
    .page-nav-link {{width:100%;min-height:44px;padding:12px 18px;display:inline-flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,.12);border-radius:999px;color:#f1f5fb;background:rgba(54,54,54,.94);box-shadow:inset 0 0 0 1px rgba(255,255,255,.03);cursor:pointer;text-decoration:none;text-align:center;font-family:"Consolas","Lucida Console",monospace;font-size:.82rem;letter-spacing:.08em;text-transform:uppercase;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease,filter .18s ease;}}
    .page-nav-link:hover,.page-nav-link:focus-visible {{transform:translateY(-1px);filter:brightness(1.06);outline:none;}}
    .page-nav-link.page-nav-map {{border-color:rgba(255,255,255,.18);background:linear-gradient(180deg,rgba(77,77,77,.96),rgba(54,54,54,.96));box-shadow:inset 0 0 0 1px rgba(255,255,255,.04),0 8px 18px rgba(0,0,0,.24);}}
    .page-nav-link.page-nav-library {{border-color:rgba(125,183,255,.45);background:linear-gradient(180deg,rgba(27,51,84,.96),rgba(18,35,58,.96));box-shadow:inset 0 0 0 1px rgba(255,255,255,.04),0 8px 18px rgba(6,14,28,.28);}}
    .page-nav-link.page-nav-production {{border-color:rgba(147,255,215,.3);background:linear-gradient(180deg,rgba(18,46,39,.96),rgba(12,29,25,.96));box-shadow:inset 0 0 0 1px rgba(255,255,255,.04),0 8px 18px rgba(0,0,0,.28);}}
    .summary-grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:18px;}}
    .summary-box {{position:relative;padding:16px 18px 18px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,rgba(8,24,21,.84),rgba(5,16,16,.72));}}
    .summary-box::before {{content:"";position:absolute;top:0;left:18px;right:18px;height:2px;background:linear-gradient(90deg,transparent,var(--line-bright),transparent);opacity:.68;}}
    .summary-box strong {{display:block;font-size:1.7rem;margin-bottom:6px;color:var(--accent);font-family:"Consolas","Lucida Console",monospace;letter-spacing:.05em;}}
    .summary-box span,.node-note {{color:var(--muted);}}
    .summary-box span {{display:block;font-size:.76rem;letter-spacing:.14em;text-transform:uppercase;}}
    .legend-row,.signature-explorer,.tab-shell {{margin-top:18px;}}
    .legend-pill {{display:inline-flex;align-items:center;gap:7px;min-height:32px;padding:6px 11px;border-radius:999px;border:1px solid rgba(255,255,255,.09);font-size:.88rem;line-height:1.2;white-space:nowrap;}}
    .legend-pill::before {{content:"";width:10px;height:10px;border-radius:999px;background:currentColor;box-shadow:0 0 14px currentColor;}}
    .legend-pill.amc-c {{color:var(--amc-c);background:rgba(43,89,88,.3);}} .legend-pill.amc-1 {{color:var(--amc-1);background:rgba(47,83,46,.28);}} .legend-pill.amc-2 {{color:var(--amc-2);background:rgba(94,68,24,.32);}} .legend-pill.amc-3 {{color:var(--amc-3);background:rgba(92,47,26,.34);}} .legend-pill.amc-i,.industrial,.node-chip.industrial {{color:var(--amc-i);background:rgba(95,31,82,.34);}} .legend-pill.amc-m {{color:var(--amc-m);background:rgba(104,34,34,.36);}} .legend-pill.raw,.badge.raw {{color:var(--raw);background:rgba(37,69,104,.42);}} .legend-pill.external,.badge.external {{color:#edf2fa;background:rgba(64,71,85,.44);}} .badge.amc {{color:#effff6;background:rgba(47,83,46,.4);}}
    .eyebrow,.workflow-eyebrow {{margin:0 0 8px;color:var(--accent);font-size:.8rem;font-family:"Consolas","Lucida Console",monospace;letter-spacing:.18em;text-transform:uppercase;}}
    .tab-shell {{padding:18px;border-radius:26px;background:linear-gradient(180deg,rgba(8,22,20,.96),rgba(5,14,15,.92));}}
    .tab-shell-header {{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,.07);}}
    .tab-shell-header h2,.tier-panel-header h2,.workflow-header h2 {{margin:0;}}
    .tab-shell-copy,.tier-panel-copy {{margin:8px 0 0;max-width:68rem;color:var(--muted);line-height:1.45;}}
    .tier-tab {{min-height:42px;padding:10px 16px;background:rgba(13,31,27,.88);cursor:pointer;letter-spacing:.08em;text-transform:uppercase;font-size:.82rem;}}
    .tier-tab.is-selected {{border-color:rgba(146,255,232,.64);background:linear-gradient(180deg,rgba(24,74,61,.95),rgba(13,45,37,.95));box-shadow:inset 0 0 0 1px rgba(255,255,255,.08),0 0 18px rgba(146,255,232,.08);}}
    .tier-panel {{margin-top:14px;--active-signature-colour:var(--accent);}}
    .view-controls {{display:flex;gap:8px;flex-wrap:wrap;}}
    .reset-view-button,.zoom-button {{cursor:pointer;background:rgba(13,31,27,.88);}}
    .root-selector {{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;}}
    .root-tag {{padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(13,31,27,.72);color:var(--text);cursor:pointer;letter-spacing:.08em;text-transform:uppercase;font-size:.8rem;}}
    .root-tag.is-selected {{border-color:rgba(146,255,232,.64);background:rgba(24,74,61,.76);box-shadow:0 0 16px rgba(146,255,232,.08);}}
    .signature-explorer {{padding:18px;border-radius:26px;background:linear-gradient(180deg,rgba(8,22,20,.96),rgba(5,14,15,.92));}}
    .signature-explorer-header {{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px;}}
    .signature-explorer-header h2 {{margin:0;}}
    .signature-explorer-copy {{margin:8px 0 0;max-width:68rem;color:var(--muted);line-height:1.45;}}
    .signature-explorer-status {{display:inline-flex;align-items:center;min-height:38px;padding:8px 14px;border:1px solid var(--line);border-radius:999px;background:rgba(13,31,27,.78);color:#d7fff2;font-size:.84rem;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;}}
    .signature-lookup {{padding:14px 16px;border:1px solid var(--line);border-radius:22px;background:rgba(9,21,20,.76);}}
    .signature-lookup + .signature-lookup {{margin-top:12px;}}
    .signature-panel-note {{margin:0 0 12px;color:var(--muted);font-size:.92rem;line-height:1.4;}}
    .signature-filter-row {{display:flex;gap:8px;flex-wrap:wrap;}}
    .signature-filter {{display:inline-flex;align-items:center;gap:8px;min-height:34px;padding:7px 11px;border:1px solid color-mix(in srgb,var(--signature-colour),rgba(255,255,255,.14) 48%);border-radius:999px;background:color-mix(in srgb,var(--signature-colour),rgba(12,24,37,.94) 84%);color:#f2fbff;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(255,255,255,.03);}}
    .signature-filter.is-selected {{border-color:color-mix(in srgb,var(--signature-colour),white 18%);box-shadow:0 0 0 1px color-mix(in srgb,var(--signature-colour),rgba(255,255,255,.2) 54%),0 0 18px color-mix(in srgb,var(--signature-colour),transparent 70%);}}
    .signature-filter-count,.signature-result-count {{display:inline-flex;align-items:center;justify-content:center;min-width:22px;min-height:22px;padding:0 7px;border-radius:999px;background:rgba(8,14,22,.42);color:#dcefff;font-size:.75rem;line-height:1;}}
    .signature-active-filters {{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px;padding:10px 12px;border:1px solid rgba(255,255,255,.08);border-radius:16px;background:rgba(12,24,37,.66);}}
    .signature-active-label {{color:#d7ebff;font-size:.82rem;font-family:"Consolas","Lucida Console",monospace;letter-spacing:.12em;text-transform:uppercase;}}
    .signature-active-list {{display:flex;gap:8px;flex-wrap:wrap;}}
    .signature-active-chip {{display:inline-flex;align-items:center;gap:7px;min-height:30px;padding:5px 10px;border:1px solid color-mix(in srgb,var(--signature-colour),rgba(255,255,255,.18) 42%);border-radius:999px;background:color-mix(in srgb,var(--signature-colour),rgba(12,24,37,.92) 82%);color:#f3fbff;font-size:.84rem;line-height:1.2;}}
    .signature-active-chip::before {{content:"";width:8px;height:8px;border-radius:999px;background:var(--signature-colour);box-shadow:0 0 12px var(--signature-colour);}}
    .signature-results {{margin-top:14px;min-height:40px;}}
    .signature-results-empty {{margin:0;color:var(--muted);font-size:.9rem;line-height:1.4;}}
    .signature-result-group {{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;align-items:start;}}
    .signature-match-card {{position:relative;display:grid;grid-template-columns:64px minmax(0,1fr);gap:12px;width:100%;padding:12px;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:linear-gradient(180deg,rgba(10,25,22,.98),rgba(6,16,16,.98));box-shadow:0 12px 26px rgba(0,0,0,.22);color:var(--text);font:inherit;text-align:left;cursor:pointer;}}
    .signature-match-card::before {{content:"";position:absolute;inset:0 auto 0 0;width:4px;border-radius:18px 0 0 18px;background:var(--line-strong);}}
    .signature-match-card.amc::before {{background:linear-gradient(180deg,var(--amc-c),var(--amc-3));}}
    .signature-match-card.raw::before {{background:var(--raw);}}
    .signature-match-card.external::before {{background:var(--external);}}
    .signature-match-media {{position:relative;display:flex;align-items:center;justify-content:center;width:64px;min-width:64px;min-height:64px;}}
    .signature-match-body {{display:flex;flex-direction:column;min-width:0;}}
    .signature-match-topline {{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:6px;}}
    .signature-match-title {{font-size:1.02rem;font-weight:700;line-height:1.2;}}
    .signature-match-facts {{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;}}
    .signature-match-note {{margin-top:10px;color:var(--muted);font-size:.83rem;line-height:1.35;}}
    .tree-viewport {{position:relative;height:min(74vh,980px);overflow:hidden;border:1px solid var(--line);border-radius:22px;background:radial-gradient(circle at top,rgba(147,255,215,.12),transparent 32%),linear-gradient(180deg,rgba(6,17,16,.98),rgba(4,10,11,.99));cursor:grab;touch-action:none;}}
    .tree-viewport::before {{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(rgba(147,255,215,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(147,255,215,.04) 1px,transparent 1px);background-size:28px 28px;opacity:.48;}}
    .tree-viewport::after {{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(180deg,rgba(255,255,255,.02),transparent 18%,transparent 82%,rgba(147,255,215,.05));}}
    .tree-viewport.is-dragging {{cursor:grabbing;}}
    .tree-surface {{position:absolute;top:0;left:0;display:flex;gap:20px;align-items:flex-start;width:max-content;padding:20px;will-change:transform;transform-origin:top left;}}
    .workflow-column {{min-width:max-content;padding:16px;border:1px solid rgba(255,255,255,.08);border-radius:22px;background:linear-gradient(180deg,rgba(9,21,20,.94),rgba(5,14,15,.9));box-shadow:0 12px 28px rgba(0,0,0,.26);}}
    .workflow-column.is-focused {{border-color:rgba(146,255,232,.62);box-shadow:0 0 0 1px rgba(146,255,232,.24),0 12px 28px rgba(0,0,0,.26);}}
    .workflow-header {{margin-bottom:14px;}} .workflow-tree {{width:max-content;}}
    .summary-pill {{color:#dcfff4;background:rgba(17,42,35,.9);letter-spacing:.08em;text-transform:uppercase;font-size:.76rem;}}
    .tree-node {{position:relative;display:flex;flex-direction:column;align-items:center;min-width:160px;}}
    .tree-node.stack-branch {{align-items:center;min-width:244px;}}
    .tree-node.lateral {{align-items:flex-start;min-width:0;padding:8px 0;}}
    .lateral-row {{display:flex;align-items:center;gap:26px;padding:4px 0;}}
    .node-card {{position:relative;display:grid;grid-template-columns:64px minmax(0,1fr);gap:10px;width:100%;max-width:256px;padding:11px;border-radius:18px;border:1px solid rgba(255,255,255,.08);background:linear-gradient(180deg,rgba(10,25,22,.98),rgba(6,16,16,.98));box-shadow:0 12px 26px rgba(0,0,0,.28);}}
    .node-card.signature-match {{border-color:color-mix(in srgb,var(--active-signature-colour),rgba(255,255,255,.18) 42%);box-shadow:0 0 0 1px color-mix(in srgb,var(--active-signature-colour),rgba(255,255,255,.14) 56%),0 0 22px color-mix(in srgb,var(--active-signature-colour),transparent 76%),0 12px 26px rgba(0,0,0,.28);}}
    .node-card::before {{content:"";position:absolute;inset:0 auto 0 0;width:4px;border-radius:18px 0 0 18px;background:var(--line-strong);}} .node-card.amc::before {{background:linear-gradient(180deg,var(--amc-c),var(--amc-3));}} .node-card.raw::before {{background:var(--raw);}} .node-card.external::before {{background:var(--external);}}
    .tree-node.stack-branch > .node-card::after {{content:"";position:absolute;top:100%;left:50%;width:3px;height:18px;border-radius:999px;transform:translateX(-50%);background:linear-gradient(180deg,var(--line-bright),var(--line-strong));box-shadow:0 0 10px rgba(116,178,234,.16);}}
    .tree-node.lateral > .lateral-row > .node-card::after {{content:"";position:absolute;top:50%;right:-26px;width:26px;height:3px;border-radius:999px;transform:translateY(-50%);background:linear-gradient(90deg,var(--line-strong),var(--line-bright));box-shadow:0 0 10px rgba(116,178,234,.18);}}
    .node-media {{position:relative;display:flex;align-items:center;justify-content:center;width:64px;min-width:64px;min-height:64px;}}
    .node-icon-glow,.node-icon-clip,.node-icon.fallback {{position:absolute;border-radius:14px;}}
    .node-icon-glow.node,.node-icon-clip.node,.node-icon.fallback.node {{inset:0;}}
    .node-icon-glow.chip,.node-icon-clip.chip,.node-icon.fallback.chip {{inset:0;}}
    .node-icon-glow {{background:radial-gradient(circle,color-mix(in srgb,var(--item-accent),transparent 72%),transparent 72%);filter:blur(8px);opacity:.9;transform:scale(.92);}}
    .node-icon-clip {{overflow:hidden;border:1px solid rgba(255,255,255,.08);background-color:rgba(8,14,22,.88);}}
    .node-icon.sprite {{position:absolute;top:0;left:0;width:128px;height:128px;background-image:url("{sprite_href}");background-repeat:no-repeat;background-size:{SPRITE_COLUMNS * 128}px {SPRITE_ROWS * 128}px;background-position:calc(var(--icon-col) * -128px) calc(var(--icon-row) * -128px);transform-origin:top left;}}
    .node-icon.sprite.node {{left:-1px;transform:scale(0.5);}}
    .node-icon.sprite.chip {{transform:scale(0.3125);}}
    .node-icon.fallback {{display:flex;align-items:center;justify-content:center;font-weight:700;background:color-mix(in srgb,var(--item-accent),#0f1c29 48%);color:#eef7ff;border:1px solid rgba(255,255,255,.08);}}
    .node-icon.fallback.node {{font-size:1.1rem;}}
    .node-icon.fallback.chip {{font-size:.95rem;}}
    .node-body {{min-width:0;}} .node-topline {{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;}} .node-title {{margin:0;font-size:1.02rem;line-height:1.2;}} .node-meta {{display:flex;flex-direction:column;gap:8px;margin-top:7px;}} .node-fact-group {{display:flex;flex-direction:column;gap:5px;}} .node-fact-title {{margin:0;color:#9fc2df;font-size:.69rem;line-height:1.2;letter-spacing:.1em;text-transform:uppercase;}} .node-facts {{display:flex;flex-wrap:wrap;gap:6px;}} .node-facts.signature-list {{gap:5px;}} .node-fact {{display:inline-flex;align-items:center;min-height:24px;padding:3px 8px;border:1px solid rgba(255,255,255,.08);border-radius:999px;background:rgba(19,36,58,.72);color:#cfe6fb;font-size:.74rem;line-height:1.2;}} .node-fact.signature {{border-color:color-mix(in srgb,var(--signature-colour),rgba(255,255,255,.16) 34%);background:color-mix(in srgb,var(--signature-colour),rgba(10,20,32,.9) 78%);color:#f3fbff;box-shadow:inset 0 0 0 1px rgba(255,255,255,.03);}} .node-note {{margin:6px 0 0;font-size:.85rem;line-height:1.35;}}
    .tree-children {{position:relative;display:flex;justify-content:center;gap:10px;margin-top:16px;padding-top:22px;isolation:isolate;}} .tree-children::before {{content:"";position:absolute;top:0;left:50%;width:2px;height:14px;transform:translateX(-50%);background:var(--line-strong);z-index:2;pointer-events:none;}} .tree-children.multi::after {{content:"";position:absolute;top:14px;left:var(--branch-start,128px);width:max(0px,calc(var(--branch-end,calc(100% - 128px)) - var(--branch-start,128px)));height:2px;background:var(--line-strong);z-index:2;pointer-events:none;}} .tree-children > .tree-node {{z-index:1;}} .tree-children.multi > .tree-node::before {{content:"";position:absolute;top:-8px;left:50%;width:2px;height:8px;transform:translateX(-50%);background:var(--line-strong);z-index:2;pointer-events:none;}} .tree-children:not(.multi)::before {{height:22px;}} .tree-children:not(.multi) > .tree-node::before {{display:none;}}
    .stack-children {{--stack-gap:14px;position:relative;display:flex;flex-direction:column;gap:var(--stack-gap);align-items:flex-start;margin-top:32px;isolation:isolate;}}
    .stack-children::before {{content:"";position:absolute;top:0;left:0;width:50%;height:3px;border-radius:999px;background:linear-gradient(90deg,var(--line-strong),var(--line-bright));box-shadow:0 0 10px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .stack-children::after {{content:"";position:absolute;top:0;left:50%;width:10px;height:10px;border-radius:999px;transform:translate(-50%,-50%);background:var(--accent);box-shadow:0 0 0 4px rgba(140,211,255,.12),0 0 14px rgba(140,211,255,.24);z-index:3;pointer-events:none;}}
    .stack-children > .tree-node {{margin-left:34px;align-items:flex-start;min-width:0;z-index:1;}}
    .stack-children > .tree-node::before {{content:"";position:absolute;top:50%;left:-34px;width:34px;height:3px;border-radius:999px;transform:translateY(-50%);background:linear-gradient(90deg,var(--line-bright),var(--line-strong));box-shadow:0 0 10px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .stack-children.multi > .tree-node::after {{content:"";position:absolute;top:calc(var(--stack-gap) / -2);bottom:calc(var(--stack-gap) / -2);left:-1px;width:3px;border-radius:999px;transform:translateX(-34px);background:linear-gradient(180deg,var(--line-bright),var(--line-strong));box-shadow:0 0 12px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .stack-children.multi > .tree-node:first-child::after {{top:0;}}
    .stack-children.multi > .tree-node:last-child::after {{bottom:50%;}}
    .stack-children.single > .tree-node {{margin-top:10px;}}
    .stack-children.single > .tree-node::after {{content:"";position:absolute;top:-10px;bottom:50%;left:-1px;width:3px;border-radius:999px;transform:translateX(-34px);background:linear-gradient(180deg,var(--line-bright),var(--line-strong));box-shadow:0 0 12px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .lateral-children {{--lateral-gap:14px;position:relative;display:flex;flex-direction:column;gap:var(--lateral-gap);padding:14px 0 14px 34px;isolation:isolate;}}
    .lateral-children.multi::after {{content:"";position:absolute;top:50%;left:0;width:10px;height:10px;border-radius:999px;transform:translate(-50%,-50%);background:var(--accent);box-shadow:0 0 0 4px rgba(140,211,255,.12),0 0 14px rgba(140,211,255,.24);z-index:3;pointer-events:none;}}
    .lateral-children > .tree-node {{z-index:1;}}
    .lateral-children > .tree-node::before {{content:"";position:absolute;top:50%;left:-34px;width:34px;height:3px;border-radius:999px;transform:translateY(-50%);background:linear-gradient(90deg,var(--line-bright),var(--line-strong));box-shadow:0 0 10px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .lateral-children.multi > .tree-node::after {{content:"";position:absolute;top:calc(var(--lateral-gap) / -2);bottom:calc(var(--lateral-gap) / -2);left:-1px;width:3px;border-radius:999px;transform:translateX(-34px);background:linear-gradient(180deg,var(--line-strong),var(--line-bright));box-shadow:0 0 12px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .lateral-children.multi > .tree-node:first-child::after {{top:50%;}}
    .lateral-children.multi > .tree-node:last-child::after {{bottom:50%;}}
    .lateral-children.single {{padding-top:0;padding-bottom:0;}}
    .lateral-children.single::before {{content:"";position:absolute;top:50%;left:0;width:34px;height:3px;border-radius:999px;transform:translateY(-50%);background:linear-gradient(90deg,var(--line-bright),var(--line-strong));box-shadow:0 0 10px rgba(116,178,234,.14);z-index:2;pointer-events:none;}}
    .lateral-children.single::after {{content:"";position:absolute;top:50%;left:0;width:8px;height:8px;border-radius:999px;transform:translate(-50%,-50%);background:var(--accent);box-shadow:0 0 0 4px rgba(140,211,255,.1);z-index:3;pointer-events:none;}}
    .lateral-children.single > .tree-node::before {{display:none;}}
    @media (max-width:1120px) {{.tree-viewport {{height:min(68vh,880px);}}}}
    @media (max-width:760px) {{.page {{width:min(100vw - 10px,1880px);margin-top:6px;}} .hero,.signature-explorer,.tab-shell {{padding:12px 18px;}} .hero-top,.tier-panel-header,.signature-explorer-header,.tab-shell-header {{flex-direction:column;align-items:flex-start;}} .hero-side {{justify-items:stretch;width:100%;}} .terminal-status {{width:100%;}} .terminal-status-row {{justify-content:flex-start;}} .tree-viewport {{height:72vh;}} .tree-surface {{padding:18px;gap:18px;}} .workflow-column {{padding:14px;}} .signature-result-group {{grid-template-columns:1fr;}}}}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-copy"><p class="eyebrow">TSN Industrial Archive</p><h1>Manufacturing Data Terminal</h1><p>Each channel loads the production schematics cleared for a specific AMC class and traces every visible dependency in that band.</p><p>Lower AMC channels halt when a dependency exceeds channel clearance. Use <strong>Show All</strong> to unlock the full archive, then drag across the schematic board to inspect each chain.</p></div>
        <div class="hero-side"><div class="terminal-status"><span class="terminal-id">Terminal // MFG-DATACORE-7</span><div class="terminal-status-row"><span class="terminal-status-pill">Archive Sync: Live</span><span class="terminal-status-pill">Source: TSN DB</span></div></div><div class="page-nav-stack"><a class="page-nav-link page-nav-map" href="index.html">Galactic Map</a><a class="page-nav-link page-nav-library" href="Library.html">Ship Library</a><button class="page-nav-link page-nav-production" type="button">Production Flow</button></div></div>
      </div>
      <div class="summary-grid">
        <div class="summary-box"><strong>{len(all_roots)}</strong><span>Tracked Outputs</span></div>
        <div class="summary-box"><strong>{len(raw_items)}</strong><span>Raw Extractions</span></div>
        <div class="summary-box"><strong>{len(external_items)}</strong><span>External Feeds</span></div>
        <div class="summary-box"><strong>{len(industrial_items)}</strong><span>IAMC Cross-Cert</span></div>
        <div class="summary-box"><strong>{len(all_items)}</strong><span>Indexed Nodes</span></div>
      </div>
      <div class="legend-row"><span class="legend-pill amc-c">AMC C</span><span class="legend-pill amc-1">AMC 1</span><span class="legend-pill amc-2">AMC 2</span><span class="legend-pill amc-3">AMC 3</span><span class="legend-pill amc-i">AMC I</span><span class="legend-pill amc-m">AMC M</span><span class="legend-pill raw">Raw Resource</span><span class="legend-pill external">External Chain</span><span class="legend-pill amc-i">Also in IAMC</span></div>
    </section>
    {signature_explorer}
    <section class="tab-shell"><div class="tab-shell-header"><div><p class="eyebrow">Schematic Bank</p><h2>Tiered Production Channels</h2><p class="tab-shell-copy">Switch AMC channels to compare which branches remain manufacturable, which dependencies fall back to raw extraction, and which routes leave the archive entirely.</p></div></div><div class="tier-tabs" role="tablist" aria-label="AMC Type Views">{tab_buttons}</div>{tab_panels}</section>
  </main>
  <script>
    const tabButtons=Array.from(document.querySelectorAll('[data-tier-tab]')); const tabPanels=Array.from(document.querySelectorAll('[data-tier-panel]')); const signaturePanels=Array.from(document.querySelectorAll('[data-signature-panel]')); const signatureExplorer=document.querySelector('.signature-explorer'); const signatureExplorerKey='all'; const panState=new Map();
    function getSurfaceBounds(state){{ const columns=Array.from(state.surface.querySelectorAll('[data-workflow-root]')); if(!columns.length) return {{left:0,top:0,right:state.surface.scrollWidth,bottom:state.surface.scrollHeight}}; const left=Math.min(...columns.map((column)=>column.offsetLeft)); const top=Math.min(...columns.map((column)=>column.offsetTop)); const right=Math.max(...columns.map((column)=>column.offsetLeft+column.offsetWidth)); const bottom=Math.max(...columns.map((column)=>column.offsetTop+column.offsetHeight)); return {{left,top,right,bottom}}; }}
    function clampPan(state){{ const bounds=getSurfaceBounds(state); const scaledLeft=bounds.left*state.scale; const scaledTop=bounds.top*state.scale; const scaledRight=bounds.right*state.scale; const scaledBottom=bounds.bottom*state.scale; const maxX=24-scaledLeft; const maxY=24-scaledTop; const minX=Math.min(maxX,state.viewport.clientWidth-scaledRight-24); const minY=Math.min(maxY,state.viewport.clientHeight-scaledBottom-24); state.x=Math.max(minX,Math.min(maxX,state.x)); state.y=Math.max(minY,Math.min(maxY,state.y)); }}
    function applyPan(state){{ clampPan(state); state.surface.style.transform=`translate(${{state.x}}px, ${{state.y}}px) scale(${{state.scale}})`; }}
    function resetPan(key){{ const state=panState.get(key); if(!state)return; state.scale=0.92; const bounds=getSurfaceBounds(state); state.x=24-(bounds.left*state.scale); state.y=24-(bounds.top*state.scale); applyPan(state); }}
    function setSelectedRoot(key, rootToken){{ document.querySelectorAll(`[data-root-selector="${{key}}"] .root-tag`).forEach((button)=>button.classList.toggle('is-selected', button.dataset.focusRoot===rootToken)); document.querySelectorAll(`[data-tier-panel="${{key}}"] [data-workflow-root]`).forEach((column)=>column.classList.toggle('is-focused', column.dataset.workflowRoot===rootToken)); }}
    function focusRoot(key, rootToken){{ const state=panState.get(key); if(!state)return; const target=state.surface.querySelector(`[data-workflow-root="${{rootToken}}"]`); if(!target)return; const bounds=getSurfaceBounds(state); state.x=(state.viewport.clientWidth/2)-((target.offsetLeft+(target.offsetWidth/2))*state.scale); state.y=Math.min(24-(bounds.top*state.scale), (state.viewport.clientHeight*0.14)-(target.offsetTop*state.scale)); applyPan(state); setSelectedRoot(key, rootToken); }}
    function zoomTier(key, direction){{ const state=panState.get(key); if(!state)return; const nextScale=direction==='in'?state.scale+0.08:state.scale-0.08; state.scale=Math.max(0.58, Math.min(1.24, Number(nextScale.toFixed(2)))); applyPan(state); }}
    function syncSignatureExplorer(){{ if(!signatureExplorer)return; signaturePanels.forEach((panel)=>{{ panel.hidden=panel.dataset.signaturePanel!==signatureExplorerKey; }}); applySignatureFilters(signatureExplorerKey); }}
    function applySignatureFilters(key){{ const lookup=document.querySelector(`[data-signature-lookup="${{key}}"]`); const panel=tabPanels.find((entry)=>!entry.hidden) || document.querySelector(`[data-tier-panel="${{key}}"]`); const status=signatureExplorer?signatureExplorer.querySelector('[data-signature-status]'):null; if(!lookup||!panel){{ if(status) status.textContent='Archive scope unavailable'; return; }} const selectedButtons=Array.from(lookup.querySelectorAll('.signature-filter.is-selected')); const selectedTokens=selectedButtons.map((button)=>button.dataset.signature); const selectedNames=selectedButtons.map((button)=>button.dataset.signatureName); const activeWrap=lookup.querySelector(`[data-signature-active="${{key}}"]`); const activeList=lookup.querySelector(`[data-signature-active-list="${{key}}"]`); const results=lookup.querySelector(`[data-signature-results="${{key}}"]`); const empty=lookup.querySelector(`[data-signature-empty="${{key}}"]`); const label=lookup.dataset.signatureLabel||key.toUpperCase(); if(activeWrap) activeWrap.hidden=!selectedTokens.length; if(activeList) activeList.innerHTML=selectedButtons.map((button)=>`<span class="signature-active-chip" style="--signature-colour:${{button.style.getPropertyValue('--signature-colour')}};">${{button.dataset.signatureName}}</span>`).join(''); let visibleCount=0; lookup.querySelectorAll('.signature-match-card').forEach((card)=>{{ const keys=card.dataset.signatureKeys||''; const visible=selectedTokens.length>0 && selectedTokens.every((token)=>keys.includes(`|${{token}}|`)); card.hidden=!visible; if(visible) visibleCount+=1; }}); if(results) results.hidden=!selectedTokens.length; if(empty){{ if(!selectedTokens.length) empty.textContent='Select one or more signature channels to query the archive.'; else if(!visibleCount) empty.textContent=`No archive entries match ${{selectedNames.join(' + ')}}.`; empty.hidden=selectedTokens.length>0 && visibleCount>0; }} const activeColour=selectedButtons.length===1?getComputedStyle(selectedButtons[0]).getPropertyValue('--signature-colour').trim():''; if(activeColour) panel.style.setProperty('--active-signature-colour',activeColour); else panel.style.removeProperty('--active-signature-colour'); panel.querySelectorAll('.node-card').forEach((card)=>{{ const keys=card.dataset.signatureKeys||''; card.classList.toggle('signature-match', selectedTokens.length>0 && selectedTokens.every((token)=>keys.includes(`|${{token}}|`))); }}); if(status){{ if(!selectedTokens.length) status.textContent=`Archive scope: ${{label}}`; else status.textContent=`Filter lock: ${{selectedNames.join(' + ')}} | ${{visibleCount}} entr${{visibleCount===1?'y':'ies'}}`; }} }}
    function toggleSignature(key, signatureToken){{ const lookup=document.querySelector(`[data-signature-lookup="${{key}}"]`); if(!lookup)return; const button=lookup.querySelector(`.signature-filter[data-signature="${{signatureToken}}"]`); if(!button)return; button.classList.toggle('is-selected'); applySignatureFilters(key); }}
    function syncPrimaryBranchConnectors(scope=document){{ scope.querySelectorAll('.tree-children.multi').forEach((branch)=>{{ const childNodes=Array.from(branch.children).filter((child)=>child.classList&&child.classList.contains('tree-node')); if(childNodes.length<2){{ branch.style.removeProperty('--branch-start'); branch.style.removeProperty('--branch-end'); return; }} const firstNode=childNodes[0]; const lastNode=childNodes[childNodes.length-1]; const start=firstNode.offsetLeft+(firstNode.offsetWidth/2); const end=lastNode.offsetLeft+(lastNode.offsetWidth/2); branch.style.setProperty('--branch-start',`${{start}}px`); branch.style.setProperty('--branch-end',`${{end}}px`); }}); }}
    function activateTier(key){{ tabButtons.forEach((button)=>{{ const selected=button.dataset.tierTab===key; button.classList.toggle('is-selected',selected); button.setAttribute('aria-selected',selected?'true':'false'); }}); tabPanels.forEach((panel)=>{{ panel.hidden=panel.dataset.tierPanel!==key; }}); syncSignatureExplorer(); requestAnimationFrame(()=>{{ const panel=document.querySelector(`[data-tier-panel="${{key}}"]`); if(panel) syncPrimaryBranchConnectors(panel); const selected=document.querySelector(`[data-root-selector="${{key}}"] .root-tag.is-selected`) || document.querySelector(`[data-root-selector="${{key}}"] .root-tag`); if(selected) focusRoot(key, selected.dataset.focusRoot); else resetPan(key); }}); }}
    document.querySelectorAll('[data-pan-viewport]').forEach((viewport)=>{{ const key=viewport.dataset.panViewport; const surface=viewport.querySelector('[data-pan-surface]'); const state={{viewport,surface,x:24,y:24,scale:0.92,startX:0,startY:0,pointerId:null}}; panState.set(key,state); applyPan(state); viewport.addEventListener('pointerdown',(event)=>{{ state.pointerId=event.pointerId; state.startX=event.clientX-state.x; state.startY=event.clientY-state.y; viewport.classList.add('is-dragging'); viewport.setPointerCapture(event.pointerId); }}); viewport.addEventListener('pointermove',(event)=>{{ if(state.pointerId!==event.pointerId)return; state.x=event.clientX-state.startX; state.y=event.clientY-state.startY; applyPan(state); }}); function releasePointer(event){{ if(state.pointerId!==event.pointerId)return; state.pointerId=null; viewport.classList.remove('is-dragging'); }} viewport.addEventListener('pointerup',releasePointer); viewport.addEventListener('pointercancel',releasePointer); viewport.addEventListener('lostpointercapture',()=>{{ state.pointerId=null; viewport.classList.remove('is-dragging'); }}); }});
    tabButtons.forEach((button)=>button.addEventListener('click',()=>activateTier(button.dataset.tierTab)));
    document.querySelectorAll('.root-tag').forEach((button)=>button.addEventListener('click',()=>focusRoot(button.dataset.focusTier, button.dataset.focusRoot)));
    document.querySelectorAll('.signature-filter').forEach((button)=>button.addEventListener('click',()=>toggleSignature(button.dataset.signatureTier, button.dataset.signature)));
    document.querySelectorAll('.signature-match-card').forEach((button)=>button.addEventListener('click',()=>{{ activateTier(button.dataset.resultTier); requestAnimationFrame(()=>focusRoot(button.dataset.resultTier, button.dataset.resultRoot)); }}));
    document.querySelectorAll('[data-reset-tier]').forEach((button)=>button.addEventListener('click',()=>resetPan(button.dataset.resetTier)));
    document.querySelectorAll('[data-zoom-tier]').forEach((button)=>button.addEventListener('click',()=>zoomTier(button.dataset.zoomTier, button.dataset.zoomDirection)));
    window.addEventListener('resize',()=>{{ panState.forEach((state)=>applyPan(state)); const panel=tabPanels.find((entry)=>!entry.hidden); if(panel) syncPrimaryBranchConnectors(panel); }});
    activateTier('c');
    ['c','1','2','3','i','m','all'].forEach((key)=>{{ const first=document.querySelector(`[data-root-selector="${{key}}"] .root-tag`); if(first) setSelectedRoot(key, first.dataset.focusRoot); }});
  </script>
</body>
</html>"""


def main():
    snapshot = parse_database_snapshot(DATABASE_PATH)
    recipes, minimum_tier, industrial_items, tier_roots = build_recipe_catalog(snapshot)
    raw_materials = set(snapshot["rawMaterials"])
    item_meta = build_item_meta(snapshot)

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        build_page(recipes, minimum_tier, raw_materials, industrial_items, item_meta, tier_roots),
        encoding="utf-8",
    )
    print(f"ProductionFlowGen summary: built 1 production flow page with {len(recipes)} recipe trees.")
    print(f"  - {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
