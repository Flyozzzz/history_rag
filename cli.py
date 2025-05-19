import argparse
import httpx
import json
import logging
from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"

async def add(args):
    logger.info("Adding message for %s", args.uuid)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {args.token}"}
        payload = {
            "uuid": args.uuid,
            "messages": [{"role": "user", "content": args.text, "type": "text"}],
            "chat_id": args.chat_id,
        }
        r = await client.post("/add", json=payload, headers=headers)
        print(r.json())

async def history(args):
    logger.info("Fetching history for %s", args.uuid)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {args.token}"}
        params = {"uuid": args.uuid, "limit": args.limit, "chat_id": args.chat_id}
        r = await client.get("/history", params=params, headers=headers)
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))

async def reminder(args):
    logger.info("Setting reminder for %s", args.uuid)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {args.token}"}
        params = {"uuid": args.uuid, "when": args.when, "text": args.text}
        r = await client.post("/reminder", params=params, headers=headers)
        print(r.json())

async def calendar(args):
    logger.info("Listing calendar for %s", args.uuid)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {args.token}"}
        params = {"uuid": args.uuid}
        r = await client.get("/calendar", params=params, headers=headers)
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))

async def update(args):
    logger.info("Updating event %s", args.index)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {args.token}"}
        payload = {"uuid": args.uuid, "text": args.text, "when": args.when}
        r = await client.put(f"/calendar/{args.index}", json=payload, headers=headers)
        print(r.json())

async def delete(args):
    logger.info("Deleting event %s", args.index)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {args.token}"}
        payload = {"uuid": args.uuid}
        r = await client.delete(f"/calendar/{args.index}", json=payload, headers=headers)
        print(r.json())

async def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    a = sub.add_parser("add")
    a.add_argument("uuid")
    a.add_argument("text")
    a.add_argument("--token", required=True)
    a.add_argument("--chat-id")

    h = sub.add_parser("history")
    h.add_argument("uuid")
    h.add_argument("--limit", type=int, default=5)
    h.add_argument("--token", required=True)
    h.add_argument("--chat-id")

    r = sub.add_parser("reminder")
    r.add_argument("uuid")
    r.add_argument("when")
    r.add_argument("text")
    r.add_argument("--token", required=True)

    c = sub.add_parser("calendar")
    c.add_argument("uuid")
    c.add_argument("--token", required=True)

    u = sub.add_parser("update")
    u.add_argument("uuid")
    u.add_argument("index", type=int)
    u.add_argument("--text")
    u.add_argument("--when")
    u.add_argument("--token", required=True)

    d = sub.add_parser("delete")
    d.add_argument("uuid")
    d.add_argument("index", type=int)
    d.add_argument("--token", required=True)

    args = parser.parse_args()
    if args.cmd == "add":
        import asyncio; asyncio.run(add(args))
    elif args.cmd == "history":
        import asyncio; asyncio.run(history(args))
    elif args.cmd == "reminder":
        import asyncio; asyncio.run(reminder(args))
    elif args.cmd == "calendar":
        import asyncio; asyncio.run(calendar(args))
    elif args.cmd == "update":
        import asyncio; asyncio.run(update(args))
    elif args.cmd == "delete":
        import asyncio; asyncio.run(delete(args))
    else:
        parser.print_help()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

