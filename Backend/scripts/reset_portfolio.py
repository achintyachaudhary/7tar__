"""Reset live-trading: clear all trades and candidates; restore 8 × ₹10L wallets."""

from app.services.live_trading import force_reset_portfolio


def main() -> None:
    result = force_reset_portfolio()
    print(result.get("message", "Portfolio reset complete."))


if __name__ == "__main__":
    main()
