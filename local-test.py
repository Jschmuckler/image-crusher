#!/usr/bin/env python
"""
Simple script to test the Cloud Function locally.
It formats the request in CloudEvent format required by functions-framework.
"""

import argparse
import json
import requests
import uuid
import datetime
import sys

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Test the file processing Cloud Function locally')
    parser.add_argument('--file-path', type=str, required=True, help='Path to the file in the bucket')
    parser.add_argument('--content-type', type=str, default='image/jpeg', help='Content type of the file')
    parser.add_argument('--port', type=int, default=8080, help='Port where the function is running')
    parser.add_argument('--height', type=int, help='Output height for processed files')
    parser.add_argument('--format', type=str, choices=['webm', 'ts'], help='Video output format (webm or ts)')
    args = parser.parse_args()

    # Format the CloudEvent
    event = {
        "specversion": "1.0",
        "id": str(uuid.uuid4()),
        "source": "//storage.googleapis.com",
        "type": "google.cloud.storage.object.v1.finalized",
        "time": datetime.datetime.now().isoformat() + "Z",
        "datacontenttype": "application/json",
        "data": {
            "name": args.file_path,
            "contentType": args.content_type
        }
    }
    
    # Add processing options if provided
    if args.height or args.format:
        event["data"]["options"] = {}
        
        if args.height:
            event["data"]["options"]["height"] = args.height
            
        if args.format:
            event["data"]["options"]["output_format"] = args.format

    # Send the request
    url = f"http://localhost:{args.port}"
    headers = {
        "Content-Type": "application/cloudevents+json"
    }
    
    print(f"Sending request to {url} with payload:")
    print(json.dumps(event, indent=2))
    
    try:
        response = requests.post(url, json=event, headers=headers)
        print(f"\nResponse status code: {response.status_code}")
        if response.text:
            print(f"Response body: {response.text}")
    except Exception as e:
        print(f"Error sending request: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()