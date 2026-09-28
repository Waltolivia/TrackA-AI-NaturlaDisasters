import argparse

from database import get_recent, initialize_database


def main():
    parser = argparse.ArgumentParser(description="View collected emergency alerts.")
    parser.add_argument("--source", choices=["NWS", "FEMA"])
    parser.add_argument("--event")
    parser.add_argument("--days", type=int)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    initialize_database()

    rows = get_recent(
        limit=args.limit,
        source=args.source,
        event=args.event,
        days=args.days,
    )

    if not rows:
        print("No alerts found.")
        return

    for row in rows:
        print("=" * 70)
        print(f"Source:       {row['source']}")
        print(f"Event:        {row['event'] or 'Unknown'}")
        print(f"Headline:     {row['headline'] or 'Unknown'}")
        print(f"Severity:     {row['severity'] or 'Unknown'}")
        print(f"Urgency:      {row['urgency'] or 'Unknown'}")
        print(f"Certainty:    {row['certainty'] or 'Unknown'}")
        print(f"Area:         {row['area'] or 'Unknown'}")
        print(f"Sent:         {row['sent'] or 'Unknown'}")
        print(f"Effective:    {row['effective'] or 'Unknown'}")
        print(f"Expires:      {row['expires'] or 'Unknown'}")
        print(f"Collected:    {row['collected_at']}")
        print(f"Sender:       {row['sender_name'] or row['sender'] or 'Unknown'}")

        if row["description"]:
            print("\nDescription:")
            print(row["description"])

        if row["instruction"]:
            print("\nInstructions:")
            print(row["instruction"])

        if row["web_url"]:
            print(f"\nSource URL:   {row['web_url']}")

    print("=" * 70)


if __name__ == "__main__":
    main()
