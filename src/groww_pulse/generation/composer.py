from collections.abc import Sequence
from datetime import date

from groww_pulse.domain.models import Action, PulseDraft, Quote, Theme, WeeklyPulse
from groww_pulse.generation.base import PulseComposer


def count_stakeholder_words(text: str) -> int:
    """Calculate word count of rendered stakeholder text."""
    # Split on whitespace to get tokens
    return len(text.split())


class StandardPulseComposer(PulseComposer):
    """Composes Markdown and email body according to standard one-page template."""

    def compose(
        self,
        week_ending: date,
        themes: Sequence[Theme],
        quotes: Sequence[Quote],
        actions: Sequence[Action],
    ) -> WeeklyPulse:
        formatted_date = week_ending.strftime("%Y-%m-%d")
        lines = [
            f"# Groww Weekly Review Pulse - Week Ending {formatted_date}",
            "",
            "## Top Themes",
        ]

        for i, theme in enumerate(themes[:3], 1):
            summary = (
                f"{theme.review_count} reviews ({int(theme.share_of_reviews * 100)}%), "
                f"avg {theme.average_rating:.1f}★, sentiment: {theme.sentiment.value}."
            )
            lines.append(f"{i}. **{theme.label}** - {summary}")

        lines.extend(["", "## What Users Said"])
        for quote in quotes[:3]:
            # Clean newlines from quote
            single_line_quote = " ".join(quote.text.split())
            lines.append(f'> "{single_line_quote}" - Anonymous Play Store review')

        lines.extend(["", "## Recommended Actions"])
        for i, action in enumerate(actions[:3], 1):
            lines.append(f"{i}. {action.description}")

        markdown = "\n".join(lines)
        word_count = count_stakeholder_words(markdown)

        return WeeklyPulse(
            week_ending=week_ending,
            top_themes=list(themes[:3]),
            quotes=list(quotes[:3]),
            actions=list(actions[:3]),
            markdown=markdown,
            word_count=word_count,
        )

    def compose_from_draft(
        self,
        week_ending: date,
        themes: Sequence[Theme],
        source_quotes: Sequence[Quote],
        actions: Sequence[Action],
        draft: PulseDraft,
    ) -> WeeklyPulse:
        """Render a structured model draft only after binding it to supplied evidence."""
        themes_by_id = {theme.id: theme for theme in themes}
        quotes_by_id = {quote.source_review_id: quote for quote in source_quotes}
        actions_by_theme = {action.theme_id: action for action in actions}

        if len(themes) != 3 or len(source_quotes) != 3 or len(actions) != 3:
            raise ValueError("Pulse source evidence must contain exactly three themes, quotes, and actions")

        rendered_themes: list[Theme] = []
        theme_summaries: list[str] = []
        for theme_draft in draft.themes:
            source_theme = themes_by_id.get(theme_draft.theme_id)
            if source_theme is None or theme_draft.label != source_theme.label:
                raise ValueError("Pulse draft references an unknown or relabeled theme")
            rendered_themes.append(source_theme)
            theme_summaries.append(theme_draft.summary)

        rendered_quotes: list[Quote] = []
        for quote_draft in draft.quotes:
            source_quote = quotes_by_id.get(quote_draft.source_review_id)
            if source_quote is None or quote_draft.quote_text not in source_quote.text:
                raise ValueError("Pulse draft contains a quote without contiguous source provenance")
            rendered_quotes.append(
                source_quote.model_copy(update={"text": quote_draft.quote_text})
            )

        rendered_actions: list[Action] = []
        for action_draft in draft.actions:
            source_action = actions_by_theme.get(action_draft.theme_id)
            if source_action is None:
                raise ValueError("Pulse draft references an action outside the selected themes")
            rendered_actions.append(
                source_action.model_copy(update={"description": action_draft.action_text})
            )

        if len({theme.id for theme in rendered_themes}) != 3:
            raise ValueError("Pulse draft must include each selected theme exactly once")
        if len({quote.source_review_id for quote in rendered_quotes}) != 3:
            raise ValueError("Pulse draft must include each selected quote exactly once")
        if len({action.theme_id for action in rendered_actions}) != 3:
            raise ValueError("Pulse draft must include one action per selected theme")
        if {action.theme_id for action in rendered_actions} != set(themes_by_id):
            raise ValueError("Pulse draft actions must cover exactly the selected themes")

        return self._render(
            week_ending, rendered_themes, rendered_quotes, rendered_actions, theme_summaries
        )

    def _render(
        self,
        week_ending: date,
        themes: Sequence[Theme],
        quotes: Sequence[Quote],
        actions: Sequence[Action],
        theme_summaries: Sequence[str] | None = None,
    ) -> WeeklyPulse:
        formatted_date = week_ending.strftime("%Y-%m-%d")
        lines = [
            f"# Groww Weekly Review Pulse - Week Ending {formatted_date}",
            "",
            "## Top Themes",
        ]
        for index, theme in enumerate(themes, 1):
            summary = (
                theme_summaries[index - 1]
                if theme_summaries is not None
                else f"{theme.review_count} reviews ({int(theme.share_of_reviews * 100)}%), "
                f"avg {theme.average_rating:.1f} stars, sentiment: {theme.sentiment.value}."
            )
            lines.append(f"{index}. **{theme.label}** - {summary}")

        lines.extend(["", "## What Users Said"])
        for quote in quotes:
            lines.append(f'> "{" ".join(quote.text.split())}" - Anonymous Play Store review')

        lines.extend(["", "## Recommended Actions"])
        for index, action in enumerate(actions, 1):
            lines.append(f"{index}. {action.description}")

        markdown = "\n".join(lines)
        return WeeklyPulse(
            week_ending=week_ending,
            top_themes=list(themes),
            quotes=list(quotes),
            actions=list(actions),
            markdown=markdown,
            word_count=count_stakeholder_words(markdown),
        )

    def render_email_body(self, pulse: WeeklyPulse, document_url: str | None = None) -> str:
        """Render consistent plain-text email body containing note and Doc link."""
        lines = [
            f"Groww Weekly Review Pulse - Week Ending {pulse.week_ending.strftime('%Y-%m-%d')}",
            "=" * 60,
            "",
        ]
        if document_url:
            lines.extend([f"Google Doc: {document_url}", ""])

        lines.append(pulse.markdown)
        return "\n".join(lines)
