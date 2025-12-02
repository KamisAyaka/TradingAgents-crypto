from tradingagents.dataflows.odaily import (
    sync_newsflash,
    sync_articles,
    get_newsflash,
    get_articles,
)


def main():
    print("Syncing Odaily RSS feeds...")
    sync_newsflash()
    sync_articles()

    flashes = get_newsflash(limit=5, lookback_hours=24, refresh=False)
    articles = get_articles(limit=3, lookback_days=7, refresh=False)

    print("\nLatest newsflashes:")
    for item in flashes:
        print(f"- {item['published']}: {item['title']}")

    print("\nLatest long-form articles:")
    for item in articles:
        print(f"- {item['published']}: {item['title']}")


if __name__ == "__main__":
    main()
