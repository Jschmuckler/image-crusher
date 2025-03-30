#!/usr/bin/env python
"""
bulk-process.py - Send a bulk processing request to the Cloud Function.
"""

import argparse
import json
import requests
import uuid
import datetime
import sys

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Bulk process images in a folder')
    parser.add_argument('--folder', type=str, help='Folder path to process (e.g., "2024/Photos")')
    parser.add_argument('--height', type=int, help='Thumbnail height (default: 256)')
    parser.add_argument('--no-recursive', action='store_true', help='Do not process subfolders')
    parser.add_argument('--port', type=int, default=8080, help='Port where the function is running')
    args = parser.parse_args()

    # Get folder path from command line or prompt
    folder_path = args.folder
    if not folder_path:
        folder_path = input("Enter folder path to process (e.g., '2024/Photos'): ")

    # Format the CloudEvent
    event = {
        "specversion": "1.0",
        "id": str(uuid.uuid4()),
        "source": "bulk-process-cli",
        "type": "bulk.process.request",
        "time": datetime.datetime.now().isoformat() + "Z",
        "datacontenttype": "application/json",
        "data": {
            "bulk_process": True,
            "folder_path": folder_path,
            "recursive": not args.no_recursive,
        }
    }

    # Add optional height if provided
    if args.height:
        event["data"]["height"] = args.height

    # Send the request
    url = f"http://localhost:{args.port}"
    headers = {
        "Content-Type": "application/cloudevents+json"
    }
    
    print("\nSending bulk processing request with payload:")
    print(json.dumps(event["data"], indent=2))
    
    try:
        print(f"\nProcessing folder: {folder_path}")
        if event["data"]["recursive"]:
            print("Including all subfolders recursively")
        else:
            print("Processing only the specified folder (non-recursive)")
            
        print("\nSending request to Cloud Function...")
        response = requests.post(url, json=event, headers=headers)
        
        print(f"Response status code: {response.status_code}")
        if response.status_code == 200:
            print("Bulk processing request sent successfully.")
            print("Check the function logs for processing status.")
        else:
            print(f"Error response: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error sending request: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()