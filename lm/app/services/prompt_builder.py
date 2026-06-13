def _fmt(value, suffix="") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value}{suffix}"


def _section(title: str, body: str) -> str:
    return f"### {title}\n{body.strip()}\n" if body.strip() else ""


def _web_section(web_results: list[dict] | None) -> str:
    if not web_results:
        return ""
    lines = []
    for w in web_results:
        meta = " · ".join(filter(None, [w.get("engine"), w.get("published")]))
        lines.append(
            f"- {w.get('title', '')}\n  {w.get('content', '')}\n  source: {w.get('url', '')}"
            + (f"  ({meta})" if meta else "")
        )
    return _section("Live web search results (fetched just now via SearXNG)", "\n".join(lines))


def _web_capability_note(web_results: list[dict] | None) -> str:
    if not web_results:
        return ""
    return (
        "\nYou have LIVE WEB SEARCH capability: the section titled "
        "'Live web search results' below was fetched from the internet moments ago "
        "via SearXNG. Use it for any current or real-time facts (latest price, recent "
        "news, today's events) and cite the source URL in parentheses when you do."
    )


def build_stock_prompt(
    symbol: str, data: dict, docs: list[dict], question: str | None,
    web_results: list[dict] | None = None,
) -> str:
    parts: list[str] = []

    profile = data.get("profile") or {}
    snapshot = data.get("snapshot") or {}
    if profile or snapshot:
        parts.append(_section("Company", "\n".join(filter(None, [
            f"Symbol: {symbol}",
            f"Name: {profile.get('company_name') or snapshot.get('company_name') or 'n/a'}",
            f"Sector: {_fmt(profile.get('sector'))} | Industry: {_fmt(profile.get('industry') or snapshot.get('industry'))}",
            f"Market cap: {_fmt(profile.get('market_cap_cr') or snapshot.get('market_cap_cr'))} Cr ({_fmt(profile.get('cap_category'))})",
            f"PE ratio: {_fmt(snapshot.get('pe_ratio'))} | ROCE: {_fmt(snapshot.get('roce_pct'), '%')}",
        ]))))

    ps = data.get("price_summary")
    if ps:
        parts.append(_section("Price action", "\n".join([
            f"Last close: {_fmt(ps['last_close'])} on {ps['last_date']}",
            f"Returns — 1W: {_fmt(ps['return_1w_pct'], '%')}, 1M: {_fmt(ps['return_1m_pct'], '%')}, "
            f"3M: {_fmt(ps['return_3m_pct'], '%')}, 1Y: {_fmt(ps['return_1y_pct'], '%')}",
            f"52-week range: {_fmt(ps['low_52w'])} – {_fmt(ps['high_52w'])}",
        ])))

    fins = data.get("financials") or {}
    if fins.get("quarterly"):
        lines = [
            f"{q['period_label']}: revenue {_fmt(q['revenue_cr'])} Cr, profit {_fmt(q['profit_cr'])} Cr"
            for q in fins["quarterly"]
        ]
        parts.append(_section("Quarterly financials (latest first)", "\n".join(lines)))
    if fins.get("yearly"):
        lines = [
            f"{y['period_label']}: revenue {_fmt(y['revenue_cr'])} Cr, profit {_fmt(y['profit_cr'])} Cr"
            for y in fins["yearly"]
        ]
        parts.append(_section("Yearly financials (latest first)", "\n".join(lines)))

    holdings = data.get("holdings")
    if holdings:
        parts.append(_section("Shareholding", ", ".join([
            f"Promoter {_fmt(holdings.get('promoter_pct'), '%')}",
            f"FII {_fmt(holdings.get('fii_pct'), '%')}",
            f"DII {_fmt(holdings.get('dii_pct'), '%')}",
            f"Public {_fmt(holdings.get('public_pct'), '%')}",
        ]) + f" (as of {holdings.get('as_of') or 'n/a'})"))

    if docs:
        chunks = "\n\n".join(
            f"[{d.get('ticker', '?')}] {d.get('title', '')}\n{d.get('text', '')}".strip()
            for d in docs
        )
        parts.append(_section("News / documents (retrieved context)", chunks))

    web = _web_section(web_results)
    if web:
        parts.append(web)

    context = "\n".join(parts) if parts else "(no structured data available for this stock)"
    user_question = question or f"Give a comprehensive investment analysis of {symbol}."

    return f"""You are a professional equity analyst covering Indian (NSE) stocks.
Prefer the structured data provided below; if a data point is missing there, you may
use the live web search results. Do not invent numbers. No personalized financial advice.{_web_capability_note(web_results)}

{context}

Question: {user_question}

Write the report in markdown with exactly these sections:
## Summary
## Bull Case
## Bear Case
## Key Risks
## Conclusion
Keep it factual, cite numbers from the data above, and keep the whole report under 500 words."""


def build_freeform_prompt(question: str, docs: list[dict], web_results: list[dict] | None = None) -> str:
    context = "\n\n".join(
        f"[{d.get('ticker', '?')}] {d.get('title', '')}\n{d.get('text', '')}".strip()
        for d in docs
    ) or "(no documents retrieved)"

    web = _web_section(web_results)

    return f"""You are a professional equity analyst. Answer using the context below.
If the local context is insufficient, use the live web search results. Say what is
missing if neither covers it. No personalized financial advice.{_web_capability_note(web_results)}

Context:
{context}
{web}
Question: {question}

Answer in concise markdown. Cite source URLs when you use live web results."""
