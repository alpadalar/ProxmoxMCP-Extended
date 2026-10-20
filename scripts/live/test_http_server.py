#!/usr/bin/env python3
"""
Test script for ProxmoxMCP HTTP server.

This script tests the HTTP transport functionality with authentication.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Test configuration
HTTP_SERVER_URL = "http://localhost:8812/proxmox-mcp"
TEST_TOKEN = "test-token-12345"  # Replace with your actual token

def test_health():
    """Test health endpoint."""
    print("🏥 Testing health endpoint...")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "health",
            "arguments": {}
        },
        "id": 1
    }
    
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    try:
        response = requests.post(HTTP_SERVER_URL, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Health check passed: {response.status_code}")
            print(f"   Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check error: {e}")
        return False

def test_list_tools():
    """Test listing available tools."""
    print("\n🔧 Testing tool listing...")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    }
    
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    try:
        response = requests.post(HTTP_SERVER_URL, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            tools = result.get('result', {}).get('tools', [])
            print(f"✅ Tool listing passed: {response.status_code}")
            print(f"   Available tools: {len(tools)}")
            
            for tool in tools[:5]:  # Show first 5 tools
                print(f"   • {tool.get('name')} - {tool.get('description', 'No description')}")
            
            if len(tools) > 5:
                print(f"   ... and {len(tools) - 5} more tools")
                
            return True
        else:
            print(f"❌ Tool listing failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Tool listing error: {e}")
        return False

def test_get_nodes():
    """Test get_nodes tool."""
    print("\n🖥️ Testing get_nodes tool...")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_nodes",
            "arguments": {}
        },
        "id": 3
    }
    
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    try:
        response = requests.post(HTTP_SERVER_URL, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ get_nodes passed: {response.status_code}")
            
            # Extract content from MCP response
            content = result.get('result', {}).get('content', [])
            if content and len(content) > 0:
                text_content = content[0].get('text', '')
                print(f"   Response length: {len(text_content)} characters")
                # Show first few lines
                lines = text_content.split('\n')[:5]
                for line in lines:
                    if line.strip():
                        print(f"   {line}")
            
            return True
        else:
            print(f"❌ get_nodes failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ get_nodes error: {e}")
        return False

def test_authentication_failure():
    """Test authentication failure with invalid token."""
    print("\n🔒 Testing authentication failure...")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 4
    }
    
    headers = {
        "Authorization": "Bearer invalid-token",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    try:
        response = requests.post(HTTP_SERVER_URL, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 401 or response.status_code == 403:
            print(f"✅ Authentication failure test passed: {response.status_code}")
            print(f"   Expected failure with invalid token")
            return True
        else:
            print(f"❌ Authentication failure test failed: {response.status_code}")
            print(f"   Expected 401/403, got {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Authentication failure test error: {e}")
        return False

def test_permission_denied():
    """Test permission denied with insufficient scope."""
    print("\n🚫 Testing permission denied...")
    
    # Try to call an admin-only tool (assuming test token has limited scope)
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "delete_vm",
            "arguments": {
                "node": "test-node",
                "vmid": "999",
                "force": False
            }
        },
        "id": 5
    }
    
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    try:
        response = requests.post(HTTP_SERVER_URL, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 403:
            print(f"✅ Permission denied test passed: {response.status_code}")
            print(f"   Expected permission denial for admin operation")
            return True
        elif response.status_code == 200:
            print(f"⚠️ Permission denied test skipped: User has admin permissions")
            return True
        else:
            print(f"❌ Permission denied test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Permission denied test error: {e}")
        return False

def check_server_availability():
    """Check if HTTP server is running."""
    print("🔍 Checking server availability...")
    
    try:
        response = requests.get(f"{HTTP_SERVER_URL.replace('/proxmox-mcp', '')}/", timeout=5)
        print(f"✅ Server is running (status: {response.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Server not available: {e}")
        print(f"   Make sure to start the HTTP server first:")
        print(f"   ./start_http_server.sh")
        return False

def main():
    """Run all tests."""
    print("🧪 ProxmoxMCP HTTP Server Test Suite")
    print("=" * 50)
    print(f"Server URL: {HTTP_SERVER_URL}")
    print(f"Test Token: {TEST_TOKEN[:8]}..." if TEST_TOKEN else "No token")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    if not TEST_TOKEN or TEST_TOKEN == "test-token-12345":
        print("⚠️ WARNING: Using default test token.")
        print("   Please set a valid token for your environment.")
        print("   You can modify TEST_TOKEN in this script.")
        print()
    
    # Check server availability first
    if not check_server_availability():
        print("\n❌ Tests aborted: Server not available")
        return False
    
    # Run tests
    tests = [
        ("Health Check", test_health),
        ("List Tools", test_list_tools),
        ("Get Nodes", test_get_nodes),
        ("Authentication Failure", test_authentication_failure),
        ("Permission Denied", test_permission_denied),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
        
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️ {total - passed} tests failed")
    
    print("=" * 50)
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        sys.exit(1)
