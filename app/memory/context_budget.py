"""ContextBudget: estimate token count and trim non-essential context when over budget.

Token estimation: ~2 Chinese characters per token (rough heuristic).
English/code tokens are ~4 chars per token. Mixed content averages ~3 chars/token.
We use a conservative 2.5 chars/token estimate.
"""

CHARS_PER_TOKEN = 2.5
DEFAULT_BUDGET = 80_000  # tokens; Claude Sonnet has 200k context, leave room for output


def estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN)


def estimate_bundle_tokens(bundle) -> int:
    """Estimate total tokens in a ContextBundle or ReviewContextBundle."""
    total = 0

    # Project info
    total += estimate_tokens(getattr(bundle.project, "premise", "") or "")
    total += estimate_tokens(getattr(bundle.project, "main_theme", "") or "")

    # World overview
    if hasattr(bundle, "world_overview") and bundle.world_overview:
        wo = bundle.world_overview
        for field in ("setting_era", "power_system", "rules_and_taboos",
                      "geography_summary", "culture_summary"):
            total += estimate_tokens(getattr(wo, field, "") or "")

    # Characters
    for c in getattr(bundle, "characters", []):
        for field in ("background", "motivation", "current_state", "speech_style"):
            total += estimate_tokens(getattr(c, field, "") or "")

    # Character states
    if hasattr(bundle, "character_states"):
        for states in bundle.character_states.values():
            for s in states:
                total += estimate_tokens(getattr(s, "current_state", "") or "")
                total += estimate_tokens(getattr(s, "change_summary", "") or "")
    if hasattr(bundle, "character_states_history"):
        for states in bundle.character_states_history.values():
            for s in states:
                total += estimate_tokens(getattr(s, "current_state", "") or "")
                total += estimate_tokens(getattr(s, "change_summary", "") or "")

    # Relationships
    for r in getattr(bundle, "relationships", []):
        total += estimate_tokens(getattr(r, "description", "") or "")

    # Events
    for e in getattr(bundle, "events", []):
        total += estimate_tokens(getattr(e, "description", "") or "")
        total += estimate_tokens(getattr(e, "title", "") or "")

    # Lore
    for l in getattr(bundle, "lore_entries", []):
        total += estimate_tokens(getattr(l, "description", "") or "")

    # Chapter summaries
    for s in getattr(bundle, "recent_chapter_summaries", []):
        total += estimate_tokens(getattr(s, "summary", "") or "")

    # Milestones
    for m in getattr(bundle, "milestones", []):
        total += estimate_tokens(getattr(m, "description", "") or "")

    # Plot lines
    for pl in getattr(bundle, "plot_lines", []):
        total += estimate_tokens(getattr(pl, "summary", "") or "")

    # Chapter content (for review)
    if hasattr(bundle, "chapter"):
        total += estimate_tokens(getattr(bundle.chapter, "content", "") or "")

    # Retrieved chunks
    for chunk in getattr(bundle, "retrieved_chunks", []):
        total += estimate_tokens(getattr(chunk, "text", "") or "")

    return total


def trim_review_context(bundle, max_tokens: int = DEFAULT_BUDGET) -> tuple:
    """Trim ReviewContextBundle to fit within token budget.

    Returns (trimmed_bundle, info_dict) where info_dict describes what was trimmed.
    Trimming priority (lowest priority first):
    1. Reduce chapter summaries to last N
    2. Reduce character state history to last 2
    3. Truncate event descriptions
    4. Truncate lore descriptions
    """
    from dataclasses import replace
    import logging

    logger = logging.getLogger(__name__)
    trimmed = {"original_tokens": 0, "final_tokens": 0, "actions": []}

    current_tokens = estimate_bundle_tokens(bundle)
    trimmed["original_tokens"] = current_tokens

    if current_tokens <= max_tokens:
        trimmed["final_tokens"] = current_tokens
        return bundle, trimmed

    # Step 1: Reduce chapter summaries to last 10
    if len(bundle.recent_chapter_summaries) > 10:
        bundle = replace(
            bundle,
            recent_chapter_summaries=bundle.recent_chapter_summaries[-10:],
        )
        action = "Trimmed chapter summaries: -> 10"
        trimmed["actions"].append(action)
        logger.info("ContextBudget: %s", action)

    current_tokens = estimate_bundle_tokens(bundle)
    if current_tokens <= max_tokens:
        trimmed["final_tokens"] = current_tokens
        return bundle, trimmed

    # Step 2: Reduce character state history to last 2
    if hasattr(bundle, "character_states_history"):
        new_history = {}
        for char_id, states in bundle.character_states_history.items():
            new_history[char_id] = states[:2]
        bundle = replace(bundle, character_states_history=new_history)
        action = "Trimmed character state history: -> 2 per character"
        trimmed["actions"].append(action)
        logger.info("ContextBudget: %s", action)

    current_tokens = estimate_bundle_tokens(bundle)
    if current_tokens <= max_tokens:
        trimmed["final_tokens"] = current_tokens
        return bundle, trimmed

    # Step 3: Reduce chapter summaries to last 5
    if len(bundle.recent_chapter_summaries) > 5:
        bundle = replace(
            bundle,
            recent_chapter_summaries=bundle.recent_chapter_summaries[-5:],
        )
        action = "Trimmed chapter summaries: -> 5"
        trimmed["actions"].append(action)

    current_tokens = estimate_bundle_tokens(bundle)
    if current_tokens <= max_tokens:
        trimmed["final_tokens"] = current_tokens
        return bundle, trimmed

    # Step 4: Reduce lore entries to 30
    if len(bundle.lore_entries) > 30:
        bundle = replace(bundle, lore_entries=bundle.lore_entries[:30])
        action = "Trimmed lore entries: -> 30"
        trimmed["actions"].append(action)

    current_tokens = estimate_bundle_tokens(bundle)
    if current_tokens <= max_tokens:
        trimmed["final_tokens"] = current_tokens
        return bundle, trimmed

    # Step 5: Reduce events to 30
    if hasattr(bundle, "events") and len(bundle.events) > 30:
        bundle = replace(bundle, events=bundle.events[:30])
        action = "Trimmed events: -> 30"
        trimmed["actions"].append(action)

    current_tokens = estimate_bundle_tokens(bundle)
    trimmed["final_tokens"] = current_tokens
    return bundle, trimmed
