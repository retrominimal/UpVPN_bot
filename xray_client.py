#!/usr/bin/env python3
"""
Xray Client Library - Unified interface for Xray management
Provides a clean, simple API for integrating Xray into other projects
"""

import json
import time
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum

# Import from existing modules
from xray_manager import (
    XrayConfig, Logger, SSHConnection, UserManager, 
    LinkGenerator, deploy as deploy_xray
)


# ====== DATA CLASSES ======
@dataclass
class XrayUser:
    """User data structure"""
    uuid: str
    email: str
    created_at: str
    flow: str = "xtls-rprx-vision"
    traffic_up: int = 0
    traffic_down: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'XrayUser':
        return cls(
            uuid=data.get('uuid', ''),
            email=data.get('email', ''),
            created_at=data.get('created_at', ''),
            flow=data.get('flow', 'xtls-rprx-vision'),
            traffic_up=data.get('traffic_up', 0),
            traffic_down=data.get('traffic_down', 0)
        )


@dataclass
class XrayServerInfo:
    """Server information structure"""
    server_ip: str
    public_key: str
    short_id: str
    sni: str
    port: int = 443
    is_deployed: bool = False


class XrayClientError(Exception):
    """Custom exception for Xray client errors"""
    pass


# ====== MAIN CLIENT CLASS ======
class XrayClient:
    """
    Unified client for Xray management
    
    Usage Examples:
    
        # Initialize client
        client = XrayClient(
            server_ip="89.191.234.223",
            username="root",
            password="your_password",
            sni="www.google.com"
        )
        
        # Deploy Xray on server
        client.deploy()
        
        # Add a user
        user = client.add_user("user@example.com")
        print(f"VLESS Link: {user.vless_link}")
        
        # List all users
        users = client.list_users()
        for user in users:
            print(f"{user.email}: {user.uuid}")
        
        # Get user link
        link = client.get_user_link("user@example.com")
        
        # Remove user
        client.remove_user("user@example.com")
        
        # Get server stats
        stats = client.get_stats()
    """
    
    def __init__(
        self,
        server_ip: str,
        username: str,
        password: str,
        sni: str = "www.google.com",
        port: int = 443,
        logger: Optional[Logger] = None
    ):
        """
        Initialize Xray client
        
        Args:
            server_ip: Server IP address
            username: SSH username (usually 'root')
            password: SSH password
            sni: SNI for Reality (default: www.google.com)
            port: Xray port (default: 443)
            logger: Optional custom logger
        """
        self.config = XrayConfig(
            server_ip=server_ip,
            username=username,
            password=password,
            sni=sni
        )
        self.port = port
        self.logger = logger or Logger("[XrayClient]")
        self._server_info: Optional[XrayServerInfo] = None
        self._cached_users: Optional[List[XrayUser]] = None
    
    # ====== DEPLOYMENT ======
    def deploy(self) -> XrayServerInfo:
        """
        Deploy Xray on the server
        
        Returns:
            XrayServerInfo: Server information after deployment
        
        Raises:
            XrayClientError: If deployment fails
        """
        self.logger.log("Starting Xray deployment...")
        
        try:
            result = deploy_xray(self.config, self.logger)
            
            self._server_info = XrayServerInfo(
                server_ip=result['server_ip'],
                public_key=result['public_key'],
                short_id=result['short_id'],
                sni=result['sni'],
                port=self.port,
                is_deployed=True
            )
            
            self.logger.success("Xray deployed successfully")
            return self._server_info
            
        except Exception as e:
            raise XrayClientError(f"Deployment failed: {e}")
    
    # ====== USER MANAGEMENT ======
    def add_user(self, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Add a new user
        
        Args:
            email: Optional email for the user (auto-generated if not provided)
        
        Returns:
            dict: User information with uuid, email, and vless_link
            None: If user creation fails
        """
        with SSHConnection(self.config, self.logger) as ssh_conn:
            user_manager = UserManager(ssh_conn, self.config)
            link_gen = LinkGenerator(self.config)
            
            user = user_manager.add_user(email)
            
            if user:
                keys = user_manager.load_keys()
                if keys:
                    link = link_gen.generate_user_link(
                        user['uuid'],
                        keys['public_key'],
                        keys['short_id']
                    )
                    user['vless_link'] = link
                    user['server_ip'] = self.config.server_ip
                    user['port'] = self.port
                
                self._cached_users = None  # Invalidate cache
                return user
        
        return None
    
    def list_users(self) -> List[XrayUser]:
        """
        List all users
        
        Returns:
            List[XrayUser]: List of users
        """
        with SSHConnection(self.config, self.logger) as ssh_conn:
            user_manager = UserManager(ssh_conn, self.config)
            users_data = user_manager.list_users()
            
            users = []
            for user_data in users_data:
                user = XrayUser.from_dict(user_data)
                
                # Get traffic stats
                traffic = self._get_user_traffic(user.email)
                user.traffic_up = traffic['uplink']
                user.traffic_down = traffic['downlink']
                
                users.append(user)
            
            self._cached_users = users
            return users
    
    def get_user(self, identifier: str) -> Optional[XrayUser]:
        """
        Get a specific user by UUID or email
        
        Args:
            identifier: User UUID or email
        
        Returns:
            XrayUser: User information or None if not found
        """
        with SSHConnection(self.config, self.logger) as ssh_conn:
            user_manager = UserManager(ssh_conn, self.config)
            user_data = user_manager.get_user_by_id(identifier)
            
            if user_data:
                user = XrayUser.from_dict(user_data)
                traffic = self._get_user_traffic(user.email)
                user.traffic_up = traffic['uplink']
                user.traffic_down = traffic['downlink']
                return user
            
            return None
    
    def get_user_link(self, identifier: str) -> Optional[str]:
        """
        Get VLESS link for a user
        
        Args:
            identifier: User UUID or email
        
        Returns:
            str: VLESS link or None if user not found
        """
        with SSHConnection(self.config, self.logger) as ssh_conn:
            user_manager = UserManager(ssh_conn, self.config)
            user = user_manager.get_user_by_id(identifier)
            
            if not user:
                return None
            
            keys = user_manager.load_keys()
            if not keys:
                return None
            
            link_gen = LinkGenerator(self.config)
            return link_gen.generate_user_link(
                user['uuid'],
                keys['public_key'],
                keys['short_id']
            )
    
    def get_user_qr_url(self, identifier: str) -> Optional[str]:
        """
        Get QR code URL for a user's VLESS link
        
        Args:
            identifier: User UUID or email
        
        Returns:
            str: QR code URL or None if user not found
        """
        link = self.get_user_link(identifier)
        if link:
            return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={link}"
        return None
    
    def remove_user(self, identifier: str) -> bool:
        """
        Remove a user by UUID or email
        
        Args:
            identifier: User UUID or email
        
        Returns:
            bool: True if successful, False otherwise
        """
        with SSHConnection(self.config, self.logger) as ssh_conn:
            user_manager = UserManager(ssh_conn, self.config)
            result = user_manager.remove_user(identifier)
            
            if result:
                self._cached_users = None  # Invalidate cache
            
            return result
    
    def user_exists(self, identifier: str) -> bool:
        """
        Check if a user exists
        
        Args:
            identifier: User UUID or email
        
        Returns:
            bool: True if user exists
        """
        return self.get_user(identifier) is not None
    
    def count_users(self) -> int:
        """
        Get total number of users
        
        Returns:
            int: Number of users
        """
        return len(self.list_users())
    
    # ====== STATISTICS ======
    def _get_user_traffic(self, email: str) -> Dict[str, int]:
        """
        Get traffic statistics for a user
        
        Args:
            email: User email
        
        Returns:
            dict: Traffic stats (uplink, downlink)
        """
        try:
            with SSHConnection(self.config, self.logger) as ssh_conn:
                user_manager = UserManager(ssh_conn, self.config)
                
                uplink = user_manager.get_user_stats_via_api(email)
                
                # Get downlink as well
                stats_cmd = f"xray api stats --name 'user>>>{email}>>>traffic>>>downlink' --server=127.0.0.1:8080"
                out, _, _ = ssh_conn.run_command(stats_cmd)
                
                downlink = 0
                if out:
                    import re
                    match = re.search(r'value:\s*(\d+)', out)
                    if match:
                        downlink = int(match.group(1))
                
                return {'uplink': uplink, 'downlink': downlink}
        except:
            return {'uplink': 0, 'downlink': 0}
    
    def get_total_traffic(self) -> Dict[str, int]:
        """
        Get total traffic across all users
        
        Returns:
            dict: Total uplink, downlink, and combined
        """
        users = self.list_users()
        total_up = sum(u.traffic_up for u in users)
        total_down = sum(u.traffic_down for u in users)
        
        return {
            'uplink': total_up,
            'downlink': total_down,
            'total': total_up + total_down
        }
    
    def get_server_info(self) -> Optional[XrayServerInfo]:
        """
        Get server information
        
        Returns:
            XrayServerInfo: Server info or None if not deployed
        """
        if self._server_info:
            return self._server_info
        
        # Try to load from server
        try:
            with SSHConnection(self.config, self.logger) as ssh_conn:
                user_manager = UserManager(ssh_conn, self.config)
                keys = user_manager.load_keys()
                
                if keys:
                    self._server_info = XrayServerInfo(
                        server_ip=self.config.server_ip,
                        public_key=keys.get('public_key', ''),
                        short_id=keys.get('short_id', ''),
                        sni=keys.get('sni', self.config.sni),
                        port=self.port,
                        is_deployed=True
                    )
                    return self._server_info
        except:
            pass
        
        return None
    
    def check_status(self) -> Dict[str, Any]:
        """
        Check Xray server status
        
        Returns:
            dict: Status information
        """
        try:
            with SSHConnection(self.config, self.logger) as ssh_conn:
                # Check if Xray is running
                _, _, exit_code = ssh_conn.run_command("pgrep xray")
                xray_running = exit_code == 0
                
                # Check API availability
                out, _, _ = ssh_conn.run_command("xray api stats --server=127.0.0.1:8080 2>&1 || true")
                api_available = "connection refused" not in out.lower()
                
                # Count users
                user_manager = UserManager(ssh_conn, self.config)
                users = user_manager.list_users()
                
                return {
                    'xray_running': xray_running,
                    'api_available': api_available,
                    'total_users': len(users),
                    'server_ip': self.config.server_ip,
                    'port': self.port
                }
        except Exception as e:
            return {
                'xray_running': False,
                'api_available': False,
                'error': str(e)
            }
    
    # ====== UTILITY METHODS ======
    def get_admin_link(self) -> Optional[str]:
        """
        Get admin VLESS link
        
        Returns:
            str: Admin VLESS link or None if not deployed
        """
        # Get first user (usually admin)
        users = self.list_users()
        if users:
            return self.get_user_link(users[0].email)
        return None
    
    def export_config(self) -> Dict[str, Any]:
        """
        Export full configuration
        
        Returns:
            dict: Complete configuration including users and server info
        """
        server_info = self.get_server_info()
        users = self.list_users()
        
        return {
            'server': asdict(server_info) if server_info else None,
            'users': [user.to_dict() for user in users],
            'total_users': len(users),
            'total_traffic': self.get_total_traffic()
        }
    
    def clear_cache(self):
        """Clear cached data"""
        self._cached_users = None


# ====== CONTEXT MANAGER ======
class XrayClientContext:
    """
    Context manager for XrayClient with automatic connection handling
    
    Usage:
        with XrayClientContext(server_ip, username, password) as client:
            users = client.list_users()
    """
    
    def __init__(self, server_ip: str, username: str, password: str, sni: str = "www.google.com"):
        self.client = XrayClient(server_ip, username, password, sni)
        self._ssh_conn = None
    
    def __enter__(self) -> XrayClient:
        return self.client
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._ssh_conn:
            self._ssh_conn.close()


# ====== HELPER FUNCTIONS ======
def create_client_from_config(config_file: str) -> XrayClient:
    """
    Create XrayClient from JSON config file
    
    Args:
        config_file: Path to JSON config file
    
    Returns:
        XrayClient: Configured client
    
    Config file format:
        {
            "server_ip": "1.2.3.4",
            "username": "root",
            "password": "your_password",
            "sni": "www.google.com",
            "port": 443
        }
    """
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    return XrayClient(
        server_ip=config['server_ip'],
        username=config['username'],
        password=config['password'],
        sni=config.get('sni', 'www.google.com'),
        port=config.get('port', 443)
    )


# ====== QUICK DEPLOYMENT ======
def quick_deploy(
    server_ip: str,
    username: str,
    password: str,
    sni: str = "www.google.com"
) -> XrayClient:
    """
    Quick one-line deployment
    
    Args:
        server_ip: Server IP address
        username: SSH username
        password: SSH password
        sni: SNI for Reality
    
    Returns:
        XrayClient: Configured and deployed client
    """
    client = XrayClient(server_ip, username, password, sni)
    client.deploy()
    return client


# ====== EXAMPLE USAGE ======
if __name__ == "__main__":
    # This is just for testing - in production, use actual credentials
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python3 xray_client.py <server_ip> <username> <password> [command]")
        print("\nCommands:")
        print("  deploy              - Deploy Xray")
        print("  add [email]         - Add user")
        print("  list                - List users")
        print("  remove <uuid/email> - Remove user")
        print("  link <uuid/email>   - Get VLESS link")
        print("  status              - Check status")
        sys.exit(1)
    
    server_ip = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    command = sys.argv[4] if len(sys.argv) > 4 else None
    
    client = XrayClient(server_ip, username, password)
    
    if command == "deploy":
        info = client.deploy()
        print(f"✅ Xray deployed!")
        print(f"Server: {info.server_ip}")
        print(f"Public Key: {info.public_key}")
        print(f"Admin Link: {client.get_admin_link()}")
    
    elif command == "add":
        email = sys.argv[5] if len(sys.argv) > 5 else None
        user = client.add_user(email)
        if user:
            print(f"✅ User added: {user['email']}")
            print(f"UUID: {user['uuid']}")
            print(f"Link: {user.get('vless_link', 'N/A')}")
        else:
            print("❌ Failed to add user")
    
    elif command == "list":
        users = client.list_users()
        print(f"\n📊 Total users: {len(users)}")
        print("-" * 80)
        for user in users:
            traffic_mb = (user.traffic_up + user.traffic_down) / (1024 * 1024)
            print(f"{user.email:<30} | {user.uuid:<36} | Traffic: {traffic_mb:.2f} MB")
    
    elif command == "remove":
        if len(sys.argv) < 6:
            print("❌ Please provide user UUID or email")
            sys.exit(1)
        if client.remove_user(sys.argv[5]):
            print(f"✅ User {sys.argv[5]} removed")
        else:
            print(f"❌ Failed to remove user {sys.argv[5]}")
    
    elif command == "link":
        if len(sys.argv) < 6:
            print("❌ Please provide user UUID or email")
            sys.exit(1)
        link = client.get_user_link(sys.argv[5])
        if link:
            print(f"🔗 VLESS Link:\n{link}")
        else:
            print(f"❌ User {sys.argv[5]} not found")
    
    elif command == "status":
        status = client.check_status()
        print("\n📊 Xray Status:")
        print(f"  Xray Running: {'✅' if status['xray_running'] else '❌'}")
        print(f"  API Available: {'✅' if status['api_available'] else '❌'}")
        print(f"  Total Users: {status.get('total_users', 0)}")
        print(f"  Server: {status.get('server_ip')}:{status.get('port')}")
    
    else:
        print(f"Unknown command: {command}")