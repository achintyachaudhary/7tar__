"""Shared news ingestion: used by the UI tools panel and scripts/ingest_news.py."""

from uuid import NAMESPACE_URL, uuid5

from app.vector.qdrant_store import upsert_document

SAMPLES = [
    {
        "ticker": "RELIANCE",
        "title": "Reliance Industries Q4 results beat estimates on retail and Jio growth",
        "text": "Reliance Industries reported consolidated net profit growth driven by strong "
                "performance in its retail and digital services (Jio) segments. The O2C (oil-to-chemicals) "
                "business saw margin pressure from weaker refining spreads, but telecom ARPU improved "
                "after tariff hikes. Management reiterated plans to scale the new energy business, "
                "including solar module and battery giga-factories.",
        "source": "sample", "date": "2026-04-25",
    },
    {
        "ticker": "TCS",
        "title": "TCS posts steady quarter; deal pipeline strong but discretionary spend cautious",
        "text": "Tata Consultancy Services reported a stable quarter with healthy order bookings. "
                "Management flagged continued caution in discretionary technology spending among North "
                "American banking clients, while demand for cost-optimization, cloud migration and "
                "GenAI-led projects remained robust. Attrition continued to trend down and the company "
                "announced a dividend.",
        "source": "sample", "date": "2026-04-12",
    },
    {
        "ticker": "INFY",
        "title": "Infosys guides for modest revenue growth amid macro uncertainty",
        "text": "Infosys issued conservative full-year revenue growth guidance citing macro uncertainty "
                "in the US and Europe. Large deal total contract value remained strong, and the company "
                "highlighted traction in its AI offerings. Margins were supported by utilization "
                "improvements and lower subcontractor costs.",
        "source": "sample", "date": "2026-04-18",
    },
    {
        "ticker": "HDFCBANK",
        "title": "HDFC Bank net interest margins stabilize as deposit growth picks up",
        "text": "HDFC Bank reported improving deposit mobilization and stabilizing net interest margins "
                "following the merger integration period. Asset quality remained healthy with low gross "
                "NPAs. Analysts noted the loan-to-deposit ratio is gradually normalizing, which should "
                "support steadier loan growth going forward.",
        "source": "sample", "date": "2026-04-20",
    },
    {
        "ticker": "TATAMOTORS",
        "title": "Tata Motors EV sales momentum continues; JLR margins improve",
        "text": "Tata Motors maintained leadership in the Indian electric passenger vehicle market while "
                "Jaguar Land Rover reported improved EBIT margins on a richer product mix and easing chip "
                "supply. The company continued to reduce automotive net debt. Commercial vehicle demand "
                "was soft quarter-on-quarter.",
        "source": "sample", "date": "2026-04-15",
    },
]


def ingest_articles(articles: list[dict]) -> list[str]:
    """Store articles in Qdrant. IDs are derived from ticker+title, so
    re-ingesting the same article updates it instead of duplicating."""
    stored = []
    for art in articles:
        ticker = art["ticker"].upper()
        point_id = str(uuid5(NAMESPACE_URL, f"{ticker}|{art.get('title', '')}"))
        upsert_document(
            art["text"],
            {
                "ticker": ticker,
                "title": art.get("title", ""),
                "source": art.get("source", "file"),
                "date": art.get("date", ""),
            },
            point_id=point_id,
        )
        stored.append(ticker)
    return stored
