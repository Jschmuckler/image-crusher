#!/usr/bin/env python
"""
Simple script to test the image processing service locally or on Cloud Run.
It formats the request in CloudEvent format required by Eventarc.
"""

import argparse
import json
import requests
import uuid
import datetime
import sys
import os

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Test the file processing service locally or on Cloud Run')
    parser.add_argument('--file-path', type=str, required=True, help='Path to the file in the bucket')
    parser.add_argument('--content-type', type=str, default='image/jpeg', help='Content type of the file')
    parser.add_argument('--port', type=int, default=8080, help='Port where the service is running (for local testing)')
    parser.add_argument('--height', type=int, help='Output height for processed files')
    parser.add_argument('--format', type=str, choices=['webm', 'ts'], help='Video output format (webm or ts)')
    parser.add_argument('--cloud-run', action='store_true', help='Test against Cloud Run service instead of local')
    parser.add_argument('--service-url', type=str, help='Cloud Run service URL (if --cloud-run is set)')
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

    # Determine URL to send the request to
    if args.cloud_run:
        if not args.service_url:
            # Try to get from environment
            service_url = os.environ.get('SERVICE_URL')
            if not service_url:
                print("Error: When using --cloud-run, you must provide --service-url or set SERVICE_URL environment variable")
                sys.exit(1)
            url = service_url
        else:
            url = args.service_url
        
        # Get ID token for authentication if testing Cloud Run
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token

            auth_req = google.auth.transport.requests.Request()
            id_token = google.oauth2.id_token.fetch_id_token(auth_req, url)
            headers = {
                "Content-Type": "application/cloudevents+json",
                "Authorization": f"Bearer {id_token}"
            }
        except ImportError:
            print("Error: To authenticate to Cloud Run, install required packages:")
            print("pip install google-auth google-auth-oauthlib google-auth-httplib2")
            sys.exit(1)
    else:
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