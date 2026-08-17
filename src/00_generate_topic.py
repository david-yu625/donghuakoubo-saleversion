"""Generate one topic that is absent from the local topic history."""

from __future__ import annotations

import argparse

from .prepare.topic_generation import generate_unique_topic


def main() -> int:
    parser = argparse.ArgumentParser(description="生成未重复的短视频主题")
    parser.add_argument("--direction", default="", help="选题大方向，例如数据库或人工智能")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    args = parser.parse_args()
    print(generate_unique_topic(
        direction=args.direction,
        api_key=args.api_key,
        model=args.model,
        base_url=args.base_url,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
