#!/usr/bin/env python3
"""
Xray CLI - Command line interface for Xray management
Can be run directly or imported as a module
"""

import sys
import time
from xray_manager import (
    XrayConfig, Logger, SSHConnection, UserManager, 
    LinkGenerator, deploy
)


# ====== CONFIGURATION ======
DEFAULT_SERVER_IP = "Your_Ip_Server"
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = "pass"
DEFAULT_SNI = "www.google.com"


def get_config():
    """Get configuration from defaults (can be overridden in imports)"""
    return XrayConfig(
        server_ip=DEFAULT_SERVER_IP,
        username=DEFAULT_USERNAME,
        password=DEFAULT_PASSWORD,
        sni=DEFAULT_SNI
    )


# ====== CLI FUNCTIONS ======
def cli_deploy():
    """Deploy Xray on server"""
    print("\n" + "="*60)
    print("=== Deploying Xray with API Support ===")
    print("="*60)
    
    config = get_config()
    logger = Logger()
    
    result = deploy(config, logger)
    
    print("\n" + "="*60)
    print("=== DEPLOYMENT COMPLETE with API Support ===")
    print("="*60)
    print(f"Server IP: {result['server_ip']}")
    print(f"Public Key: {result['public_key']}")
    print(f"Short ID: {result['short_id']}")
    print(f"SNI: {result['sni']}")
    print(f"\nXray API: 127.0.0.1:8080 (gRPC)")
    print("\n--- Admin User ---")
    print(f"UUID: {result['admin_user']['uuid']}")
    print(f"Email: {result['admin_user']['email']}")
    print(f"\n=== VLESS LINK ===")
    print(result['link'])
    print("\n" + "="*60)
    print("✅ Users can now be added/removed WITHOUT connection drops!")
    print("To add more users, run: python3 xray_cli.py add")
    print("="*60)


def cli_add_user(email=None):
    """Add a new user"""
    config = get_config()
    logger = Logger()
    
    with SSHConnection(config, logger) as ssh_conn:
        user_manager = UserManager(ssh_conn, config)
        link_gen = LinkGenerator(config)
        
        user = user_manager.add_user(email)
        
        if user:
            keys = user_manager.load_keys()
            if keys:
                link = link_gen.generate_user_link(
                    user['uuid'], 
                    keys['public_key'], 
                    keys['short_id']
                )
                
                print(f"\n✅ User added successfully!")
                print(f"UUID: {user['uuid']}")
                print(f"Email: {user['email']}")
                print(f"\n🔗 VLESS Link:\n{link}")
                print(f"\n📱 QR Code URL:")
                print(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={link}")
            else:
                print(f"\n✅ User added successfully!")
                print(f"UUID: {user['uuid']}")
                print(f"Email: {user['email']}")
        else:
            print("\n❌ Failed to add user")


def cli_list_users():
    """List all users"""
    config = get_config()
    logger = Logger()
    
    with SSHConnection(config, logger) as ssh_conn:
        user_manager = UserManager(ssh_conn, config)
        users = user_manager.list_users()
        
        if not users:
            print("\nNo users found")
            return
        
        print("\n" + "="*90)
        print(f"{'#':<4} {'UUID':<38} {'Email':<30} {'Created At':<20}")
        print("="*90)
        
        for idx, user in enumerate(users, 1):
            print(f"{idx:<4} {user['uuid']:<38} {user.get('email', 'N/A'):<30} {user.get('created_at', 'N/A'):<20}")
        
        print("="*90)
        print(f"Total users: {len(users)}")


def cli_remove_user(user_id):
    """Remove a user by UUID or email"""
    config = get_config()
    logger = Logger()
    
    with SSHConnection(config, logger) as ssh_conn:
        user_manager = UserManager(ssh_conn, config)
        
        if user_manager.remove_user(user_id):
            print(f"\n✅ User {user_id} removed successfully!")
        else:
            print(f"\n❌ Failed to remove user {user_id}")


def cli_show_link(user_id):
    """Show VLESS link for a user"""
    config = get_config()
    logger = Logger()
    
    with SSHConnection(config, logger) as ssh_conn:
        user_manager = UserManager(ssh_conn, config)
        user = user_manager.get_user_by_id(user_id)
        
        if not user:
            print(f"\n❌ User {user_id} not found")
            return
        
        keys = user_manager.load_keys()
        if not keys:
            print("\n❌ Keys not found!")
            return
        
        link_gen = LinkGenerator(config)
        link = link_gen.generate_user_link(
            user['uuid'], 
            keys['public_key'], 
            keys['short_id']
        )
        
        print("\n" + "="*60)
        print(f"User: {user.get('email', user['uuid'])}")
        print(f"UUID: {user['uuid']}")
        print(f"Created: {user.get('created_at', 'N/A')}")
        print("\n=== VLESS LINK ===")
        print(link)
        print("\n📱 QR Code URL:")
        print(f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={link}")
        print("="*60)


def show_usage():
    """Show usage information"""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║         Xray User Management (with API support)              ║
╚═══════════════════════════════════════════════════════════════╝

Usage:
    python3 xray_cli.py deploy                 - Deploy Xray on server
    python3 xray_cli.py add [email]            - Add new user
    python3 xray_cli.py list                   - List all users
    python3 xray_cli.py remove <uuid/email>    - Remove user
    python3 xray_cli.py link <uuid/email>      - Show VLESS link

Note: 
    - API method is preferred (no connection drops)
    - If API fails, graceful reload is used as fallback
    
Import Examples:
    from xray_manager import XrayConfig, SSHConnection, UserManager, deploy
    
    # Deploy new server
    config = XrayConfig(server_ip="1.2.3.4", username="root", password="pass")
    result = deploy(config)
    
    # Manage users
    with SSHConnection(config) as ssh:
        user_manager = UserManager(ssh, config)
        user = user_manager.add_user("user@example.com")
        users = user_manager.list_users()
""")


# ====== MAIN ======
def main():
    if len(sys.argv) < 2:
        show_usage()
        return
    
    command = sys.argv[1]
    
    try:
        if command == "deploy":
            cli_deploy()
        elif command == "add":
            email = sys.argv[2] if len(sys.argv) > 2 else None
            cli_add_user(email)
        elif command == "list":
            cli_list_users()
        elif command == "remove":
            if len(sys.argv) < 3:
                print("❌ Please provide user UUID or email to remove")
                return
            cli_remove_user(sys.argv[2])
        elif command == "link":
            if len(sys.argv) < 3:
                print("❌ Please provide user UUID or email")
                return
            cli_show_link(sys.argv[2])
        else:
            show_usage()
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()