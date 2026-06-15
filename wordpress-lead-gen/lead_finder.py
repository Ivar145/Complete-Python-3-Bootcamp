"""
WordPress Freelance Lead Finder
Finds local businesses with no website using Google Places API.
Usage: python lead_finder.py --location "Chicago, IL" --category "barber"
"""

import argparse
import csv
import os
import time
from datetime import datetime
from typing import Callable, Optional


import requests


PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def search_places(query: str, api_key: str, page_token: str = None) -> dict:
    params = {"query": query, "key": api_key}
    if page_token:
        params["pagetoken"] = page_token
    response = requests.get(PLACES_SEARCH_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def get_place_details(place_id: str, api_key: str) -> dict:
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,url,business_status",
        "key": api_key,
    }
    response = requests.get(PLACES_DETAILS_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("result", {})


def find_leads(
    location: str,
    category: str,
    api_key: str,
    max_results: int = 60,
    include_with_website: bool = False,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> list[dict]:
    query = f"{category} in {location}"

    def log(message: str, current: int = 0, total: int = 0):
        if progress_callback:
            progress_callback(message, current, total)
        else:
            print(message)

    log(f"Searching: {query}", 0, max_results)

    leads = []
    checked = 0
    page_token = None

    while checked < max_results:
        data = search_places(query, api_key, page_token)
        status = data.get("status")

        if status not in ("OK", "ZERO_RESULTS"):
            log(f"API error: {status} — {data.get('error_message', '')}", checked, max_results)
            break

        results = data.get("results", [])
        if not results:
            break

        for place in results:
            if checked >= max_results:
                break

            checked += 1
            place_id = place["place_id"]
            name = place.get("name", "")

            details = get_place_details(place_id, api_key)

            if details.get("business_status") == "CLOSED_PERMANENTLY":
                log(f"[{checked}/{max_results}] {name} — closed, skipping", checked, max_results)
                continue

            website = details.get("website", "")
            lead = {
                "name": details.get("name", name),
                "address": details.get("formatted_address", place.get("formatted_address", "")),
                "phone": details.get("formatted_phone_number", ""),
                "website": website,
                "google_maps_url": details.get("url", f"https://maps.google.com/?place_id={place_id}"),
                "category": category,
                "location": location,
            }

            if not website:
                log(f"[{checked}/{max_results}] {name} — NO WEBSITE", checked, max_results)
                leads.append(lead)
            elif include_with_website:
                log(f"[{checked}/{max_results}] {name} — has website", checked, max_results)
                leads.append(lead)
            else:
                log(f"[{checked}/{max_results}] {name} — has website, skipping", checked, max_results)

            time.sleep(0.1)

        page_token = data.get("next_page_token")
        if not page_token:
            break

        time.sleep(2)

    return leads


def save_to_csv(leads: list[dict], output_path: str):
    no_website = [l for l in leads if not l.get("website")]
    if not no_website:
        print("\nNo leads found with missing websites.")
        return

    fieldnames = ["name", "category", "address", "phone", "website", "google_maps_url", "location"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(no_website)

    print(f"\nSaved {len(no_website)} leads to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Find local businesses with no website.")
    parser.add_argument("--location", required=True, help='City/area to search, e.g. "Chicago, IL"')
    parser.add_argument("--category", required=True, help='Business type, e.g. "barber" or "dentist"')
    parser.add_argument("--api-key", default=os.environ.get("GOOGLE_PLACES_API_KEY"), help="Google Places API key")
    parser.add_argument("--max", type=int, default=60, help="Max businesses to check (default: 60)")
    parser.add_argument("--output", default=None, help="Output CSV filename (auto-generated if omitted)")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: provide --api-key or set GOOGLE_PLACES_API_KEY environment variable.")
        return

    leads = find_leads(args.location, args.category, args.api_key, args.max)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = args.output or f"leads_{args.category.replace(' ', '_')}_{timestamp}.csv"
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    save_to_csv(leads, output_path)

    no_website_count = sum(1 for l in leads if not l.get("website"))
    print(f"\nSummary: {no_website_count} businesses found with no website out of {args.max} checked.")


if __name__ == "__main__":
    main()
