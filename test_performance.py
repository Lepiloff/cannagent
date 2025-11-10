#!/usr/bin/env python3
"""
Performance testing script for Canagent API
Measures execution time of each query stage
"""

import requests
import json
import time
import sys
import logging
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)

# API Configuration
API_BASE_URL = "http://localhost:8001"
CHAT_ENDPOINT = f"{API_BASE_URL}/api/v1/chat/ask/"

# Test queries in both languages
TEST_QUERIES = [
    # Spanish queries
    {
        "message": "Recomiéndame cepas índica con alto THC para dormir bien",
        "language": "Spanish",
        "category": "Sleep (High THC)",
    },
    {
        "message": "Necesito algo para la creatividad y el enfoque",
        "language": "Spanish",
        "category": "Creativity/Focus",
    },
    # English queries
    {
        "message": "Find me a hybrid strains with high level thc and terpenes that help with anxiety",
        "language": "English",
        "category": "Anxiety (High THC, Hybrid)",
    },
    {
        "message": "I need something energizing for work and focus",
        "language": "English",
        "category": "Energy/Focus",
    },
    # Complex query
    {
        "message": "¿Cuál de estas tiene los terpenos más relajantes para dormir?",
        "language": "Spanish",
        "category": "Terpene Query (Follow-up)",
    },
]


class PerformanceTester:
    def __init__(self):
        self.results: list[Dict[str, Any]] = []
        self.session_ids: Dict[str, str] = {}

    def test_query(self, query_data: Dict[str, str], use_session: bool = False) -> Dict[str, Any]:
        """Test a single query and measure performance"""

        logger.info("\n" + "="*80)
        logger.info(f"🧪 Testing: {query_data['category']}")
        logger.info(f"Language: {query_data['language']}")
        logger.info(f"Query: {query_data['message']}")
        logger.info("="*80)

        payload = {
            "message": query_data["message"],
            "session_id": None,
            "history": [],
            "source_platform": "test"
        }

        # Use session from previous query if requested
        if use_session and query_data['category'] in self.session_ids:
            payload["session_id"] = self.session_ids[query_data['category']]
            logger.info(f"Using existing session: {payload['session_id']}")

        # Measure total request time
        start_time = time.time()

        try:
            response = requests.post(
                CHAT_ENDPOINT,
                json=payload,
                timeout=120  # 2 minute timeout
            )

            elapsed_time = time.time() - start_time

            if response.status_code == 200:
                data = response.json()

                # Store session ID for follow-up queries
                session_id = data.get("session_id")
                if session_id:
                    self.session_ids[query_data['category']] = session_id

                result = {
                    "category": query_data['category'],
                    "language": query_data['language'],
                    "total_time_sec": round(elapsed_time, 3),
                    "status_code": 200,
                    "strains_count": len(data.get("recommended_strains", [])),
                    "confidence": data.get("confidence", 0),
                    "detected_intent": data.get("detected_intent", "unknown"),
                    "query_type": data.get("query_type", "unknown"),
                }

                logger.info(f"✅ Success: {elapsed_time:.2f}s | {result['strains_count']} strains | Confidence: {result['confidence']:.2f}")
                logger.info(f"   Intent: {result['detected_intent']} | Type: {result['query_type']}")

                # Print sample strain names
                strains = data.get("recommended_strains", [])
                if strains:
                    strain_names = ", ".join([s["name"] for s in strains[:3]])
                    logger.info(f"   Strains: {strain_names}" + ("..." if len(strains) > 3 else ""))

                return result

            else:
                logger.error(f"❌ Error: Status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return {
                    "category": query_data['category'],
                    "language": query_data['language'],
                    "total_time_sec": elapsed_time,
                    "status_code": response.status_code,
                    "error": response.text
                }

        except requests.exceptions.Timeout:
            elapsed_time = time.time() - start_time
            logger.error(f"❌ Timeout after {elapsed_time:.2f}s")
            return {
                "category": query_data['category'],
                "language": query_data['language'],
                "total_time_sec": elapsed_time,
                "status_code": 0,
                "error": "Request timeout"
            }
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"❌ Exception: {str(e)}")
            return {
                "category": query_data['category'],
                "language": query_data['language'],
                "total_time_sec": elapsed_time,
                "status_code": -1,
                "error": str(e)
            }

    def run_all_tests(self):
        """Run all test queries"""
        logger.info("\n\n" + "█"*80)
        logger.info("🚀 CANAGENT PERFORMANCE TEST SUITE")
        logger.info(f"📅 Started: {datetime.now().isoformat()}")
        logger.info(f"🔗 API: {API_BASE_URL}")
        logger.info("█"*80 + "\n")

        # Test initial queries
        logger.info("📋 PHASE 1: Initial queries (cold start)")
        logger.info("-"*80)
        for i, query in enumerate(TEST_QUERIES[:3], 1):
            result = self.test_query(query)
            self.results.append(result)

        # Test follow-up queries with session
        logger.info("\n📋 PHASE 2: Follow-up queries (warm session)")
        logger.info("-"*80)
        result = self.test_query(TEST_QUERIES[4], use_session=True)
        self.results.append(result)

        # Print summary report
        self._print_summary()

    def _print_summary(self):
        """Print performance summary"""
        logger.info("\n\n" + "█"*80)
        logger.info("📊 PERFORMANCE SUMMARY")
        logger.info("█"*80 + "\n")

        # Group by status
        successful = [r for r in self.results if r.get("status_code") == 200]
        failed = [r for r in self.results if r.get("status_code") != 200]

        logger.info(f"Total queries: {len(self.results)}")
        logger.info(f"✅ Successful: {len(successful)}")
        logger.info(f"❌ Failed: {len(failed)}")

        if successful:
            times = [r["total_time_sec"] for r in successful]
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)

            logger.info(f"\n⏱️  RESPONSE TIMES:")
            logger.info(f"   Average: {avg_time:.2f}s")
            logger.info(f"   Fastest: {min_time:.2f}s")
            logger.info(f"   Slowest: {max_time:.2f}s")

        logger.info("\n📈 DETAILED RESULTS:")
        logger.info("-"*80)
        logger.info(f"{'Category':<35} | {'Time':>7} | {'Status':>6} | {'Strains':>7}")
        logger.info("-"*80)

        for result in self.results:
            status = "✅" if result.get("status_code") == 200 else "❌"
            time_str = f"{result['total_time_sec']:.2f}s"
            strains = result.get("strains_count", "N/A")
            category = result.get("category", "Unknown")[:32]

            logger.info(f"{category:<35} | {time_str:>7} | {status:>6} | {strains:>7}")

        logger.info("-"*80)

        # Performance analysis
        logger.info("\n⚠️  PERFORMANCE ANALYSIS:")
        if successful:
            slow_queries = [r for r in successful if r["total_time_sec"] > 5]
            if slow_queries:
                logger.warning(f"   {len(slow_queries)} query(ies) took > 5 seconds:")
                for r in slow_queries:
                    logger.warning(f"     • {r['category']}: {r['total_time_sec']:.2f}s")
            else:
                logger.info("   ✅ All queries completed in < 5 seconds")

        logger.info("\n💡 CHECK THE API LOGS FOR DETAILED STAGE TIMINGS")
        logger.info("   (Look for the performance profiling output from /api/v1/chat/ask/)")

        logger.info("\n" + "█"*80 + "\n")


def main():
    """Main test function"""

    # Check if API is available
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/ping/", timeout=5)
        if response.status_code != 200:
            logger.error(f"❌ API not responding correctly (status: {response.status_code})")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Cannot connect to API at {API_BASE_URL}")
        logger.error(f"   Make sure the API is running: make start")
        logger.error(f"   Error: {e}")
        sys.exit(1)

    logger.info("✅ API is responding")

    # Run tests
    tester = PerformanceTester()
    tester.run_all_tests()

    # Exit with success
    sys.exit(0)


if __name__ == "__main__":
    main()
