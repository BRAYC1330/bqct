import os
import sys
import asyncio
import logging
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    import config
    import generator_gemma as gen
    from search_chainbase import fetch_trends

    test_type = os.getenv("TEST_TYPE", "digest_mini")
    test_query = os.getenv("TEST_QUERY", "What do you think about BTC?")

    logger.info(f"[TEST] Loading Gemma 4 model...")
    llm = gen.get_model()
    if not llm:
        logger.error("[TEST] Failed to load model")
        sys.exit(1)

    if test_type in ("digest_mini", "digest_full"):
        logger.info(f"[TEST] Fetching trends...")
        trends = await fetch_trends()
        if not trends:
            logger.error("[TEST] No trends")
            sys.exit(1)
        logger.info(f"[TEST] Got {len(trends)} trends")

        import build_content
        final_post, embed = await build_content.build_digest(llm, trends, test_type, client=None)
        if final_post:
            logger.info(f"[TEST] === DIGEST OUTPUT ===")
            logger.info(final_post)
            logger.info(f"[TEST] === END ===")
        else:
            logger.warning("[TEST] build_digest returned None")

    elif test_type == "comment_reply":
        logger.info(f"[TEST] Testing comment reply: '{test_query}'")
        intent = gen.classify_intent(llm, test_query, "Bitcoin ETF approval news")
        logger.info(f"[TEST] Intent: {intent}")
        sentiment = gen.classify_sentiment(llm, test_query, "Bitcoin ETF approval news")
        logger.info(f"[TEST] Sentiment: {sentiment}")
        reply = gen.get_answer(llm, "[ROOT]\nBitcoin ETF approval news", test_query, prompt_key="community_reply")
        logger.info(f"[TEST] === REPLY ===")
        logger.info(reply)
        logger.info(f"[TEST] === END ===")

    logger.info("[TEST] Done")

if __name__ == "__main__":
    asyncio.run(main())
