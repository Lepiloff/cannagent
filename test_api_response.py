#!/usr/bin/env python3
"""
Test script to check API response format
"""
import requests
import json

API_URL = "http://localhost:8001/api/v1/chat/ask/"

# Test query
test_query = {
    "message": "find me sativa strains with low thc"
}

print("=" * 80)
print("Testing API Response Format")
print("=" * 80)

try:
    response = requests.post(API_URL, json=test_query, timeout=30)

    print(f"\nStatus Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()

        print(f"\nResponse keys: {list(data.keys())}")
        print(f"\nNumber of recommended strains: {len(data.get('recommended_strains', []))}")

        # Print first strain in detail
        if data.get('recommended_strains'):
            first_strain = data['recommended_strains'][0]
            print("\n" + "=" * 80)
            print("FIRST STRAIN DETAILS:")
            print("=" * 80)
            print(json.dumps(first_strain, indent=2, default=str))

            # Check if relationships are present
            print("\n" + "=" * 80)
            print("RELATIONSHIPS CHECK:")
            print("=" * 80)
            print(f"✓ Feelings count: {len(first_strain.get('feelings', []))}")
            print(f"✓ Helps with count: {len(first_strain.get('helps_with', []))}")
            print(f"✓ Negatives count: {len(first_strain.get('negatives', []))}")
            print(f"✓ Flavors count: {len(first_strain.get('flavors', []))}")

            if first_strain.get('feelings'):
                print("\nFeelings:")
                for f in first_strain['feelings']:
                    print(f"  - {f}")

            if first_strain.get('helps_with'):
                print("\nHelps with:")
                for h in first_strain['helps_with']:
                    print(f"  - {h}")

            if first_strain.get('flavors'):
                print("\nFlavors:")
                for fl in first_strain['flavors']:
                    print(f"  - {fl}")

        print("\n" + "=" * 80)
        print("FULL RESPONSE:")
        print("=" * 80)
        print(json.dumps(data, indent=2, default=str))

    else:
        print(f"\nError: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
