import sys
import os
import asyncio
import logging
import getpass
import importlib.util

# Setup paths
current_dir = os.getcwd()
component_dir = os.path.join(current_dir, "custom_components", "edgerouter")

# Helper to import file directly
def import_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# Configure logging
logging.basicConfig(level=logging.DEBUG)

async def main():
    print("=== Testing API Locally ===")
    
    # Import api.py directly, bypassing __init__.py and homeassistant deps
    api_path = os.path.join(component_dir, "api.py")
    print(f"Loading API from: {api_path}")
    
    try:
        api_module = import_from_path("edgerouter_api", api_path)
        EdgeRouterAPI = api_module.EdgeRouterAPI
    except Exception as e:
        print(f"Failed to load API module: {e}")
        return

    host = "192.168.1.1" # Default
    user = "em"          # Default
    
    # Allow overriding defaults
    # host = input(f"Enter Host [{host}]: ") or host
    # user = input(f"Enter User [{user}]: ") or user
    password = getpass.getpass(f"Enter password for {user}@{host}: ")
    
    api = EdgeRouterAPI(host, user, password)
    
    print("\n[1] Validating Connection...")
    try:
        api.validate_connection()
        print("    Success!")
    except Exception as e:
        print(f"    Failed: {e}")
        return

    print("\n[2] Fetching Data (Sync Wrapper)...")
    try:
        data = api._get_data_sync()
        print("\n[3] Data Result:")
        print(f"    Uptime: {data.get('uptime')}")
        print(f"    System Image: {data.get('system_image')}")
        print(f"    Errors: {data.get('errors')}")
        print(f"    CPU: {data.get('cpu')}%")
        print(f"    Memory: {data.get('memory')}%")
        
        interfaces = data.get('interfaces', {})
        print(f"    Interfaces: {len(interfaces)} found")
        for iface, rates in interfaces.items():
            print(f"      - {iface}: RX {rates['rx']:.2f} Mbps, TX {rates['tx']:.2f} Mbps")
            
    except Exception as e:
        print(f"    Error fetching: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
