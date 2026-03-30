#!/usr/bin/env python3
"""
Xray Manager Module - Reusable components for Xray management
Provides SSH connection, Xray operations, and user management functions
"""

import paramiko
import time
import json
import uuid
import random
import base64
import re
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization


# ====== CONFIGURATION CLASS ======
class XrayConfig:
    """Configuration container for Xray deployment"""
    def __init__(self, server_ip=None, username=None, password=None, sni="www.google.com"):
        self.server_ip = server_ip
        self.username = username
        self.password = password
        self.sni = sni
        self.users_file = "/etc/xray/users.json"
        self.keys_file = "/etc/xray/keys.json"
        self.xray_config = "/usr/local/etc/xray/config.json"
    
    @classmethod
    def from_dict(cls, config_dict):
        """Create config from dictionary"""
        return cls(
            server_ip=config_dict.get('server_ip'),
            username=config_dict.get('username'),
            password=config_dict.get('password'),
            sni=config_dict.get('sni', "www.google.com")
        )


# ====== LOGGING ======
class Logger:
    """Simple logger with configurable output"""
    def __init__(self, prefix="[LOG]"):
        self.prefix = prefix
        self.enabled = True
    
    def log(self, msg):
        if self.enabled:
            print(f"{self.prefix} {msg}")
    
    def error(self, msg):
        print(f"[ERROR] {msg}")
    
    def success(self, msg):
        print(f"[SUCCESS] {msg}")


# ====== HELPERS ======
def random_short_id(length=8):
    """Generate random short ID for Reality"""
    return ''.join(random.choices('abcdef0123456789', k=length))


def generate_uuid():
    """Generate UUID v4"""
    return str(uuid.uuid4())


def generate_reality_keys():
    """Generate X25519 key pair for Reality"""
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )

    private_b64 = base64.urlsafe_b64encode(private_bytes).decode().rstrip("=")
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip("=")

    return private_b64, public_b64


# ====== SSH CONNECTION ======
class SSHConnection:
    """SSH connection manager"""
    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger or Logger()
        self.ssh = None
    
    def connect(self):
        """Establish SSH connection"""
        self.logger.log("Connecting SSH...")
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            self.config.server_ip,
            username=self.config.username,
            password=self.config.password
        )
        return self.ssh
    
    def close(self):
        """Close SSH connection"""
        if self.ssh:
            self.ssh.close()
    
    def run_command(self, command, check_error=False):
        """Execute command on remote server"""
        self.logger.log(f"RUN: {command}")
        stdin, stdout, stderr = self.ssh.exec_command(command)
        out = stdout.read().decode()
        err = stderr.read().decode()
        exit_code = stdout.channel.recv_exit_status()

        if out:
            self.logger.log(f"OUT: {out.strip()}")
        if err:
            self.logger.log(f"ERR: {err.strip()}")

        if check_error and exit_code != 0:
            raise Exception(f"Command failed with exit code {exit_code}: {err}")

        return out, err, exit_code
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ====== XRAY INSTALLATION ======
class XrayInstaller:
    """Handles Xray installation and removal"""
    def __init__(self, ssh_conn):
        self.ssh_conn = ssh_conn
        self.logger = ssh_conn.logger
    
    def remove_xray(self):
        """Remove existing Xray installation"""
        self.logger.log("Removing existing Xray (if any)...")
        
        self.ssh_conn.run_command("systemctl stop xray || true")
        self.ssh_conn.run_command("systemctl disable xray || true")
        self.ssh_conn.run_command("rm -rf /usr/local/bin/xray")
        self.ssh_conn.run_command("rm -rf /etc/xray")
        self.ssh_conn.run_command("rm -rf /var/log/xray")
        self.ssh_conn.run_command("rm -rf /usr/local/etc/xray")
    
    def install_xray(self):
        """Install Xray from official script"""
        self.logger.log("Installing Xray...")
        cmd = "bash <(curl -Ls https://github.com/XTLS/Xray-install/raw/main/install-release.sh)"
        self.ssh_conn.run_command(cmd)
    
    def wait_for_xray(self):
        """Wait for Xray to be installed"""
        self.logger.log("Waiting for Xray...")
        
        for _ in range(15):
            out, _, _ = self.ssh_conn.run_command("which xray")
            if "/xray" in out:
                self.logger.log("Xray installed")
                return
            time.sleep(1)
        
        raise Exception("Xray not found")


# ====== USER MANAGEMENT ======
class UserManager:
    """Manages Xray users"""
    def __init__(self, ssh_conn, config):
        self.ssh_conn = ssh_conn
        self.config = config
        self.logger = ssh_conn.logger
    
    def save_users(self, users):
        """Save users list to server"""
        users_json = json.dumps(users, indent=2)
        
        self.ssh_conn.run_command("mkdir -p /etc/xray")
        
        cmd = f"""cat << 'EOF' > {self.config.users_file}
{users_json}
EOF"""
        self.ssh_conn.run_command(cmd)
    
    def save_keys(self, private_key, public_key, short_id):
        """Save Reality keys to server"""
        keys_data = {
            "private_key": private_key,
            "public_key": public_key,
            "short_id": short_id,
            "sni": self.config.sni
        }
        keys_json = json.dumps(keys_data, indent=2)
        
        self.ssh_conn.run_command("mkdir -p /etc/xray")
        
        cmd = f"""cat << 'EOF' > {self.config.keys_file}
{keys_json}
EOF"""
        self.ssh_conn.run_command(cmd)
    
    def load_users(self):
        """Load users from server"""
        try:
            out, _, _ = self.ssh_conn.run_command(f"cat {self.config.users_file} 2>/dev/null || echo '[]'")
            return json.loads(out)
        except:
            return []
    
    def load_keys(self):
        """Load keys from server"""
        try:
            out, _, _ = self.ssh_conn.run_command(f"cat {self.config.keys_file} 2>/dev/null || echo '{{}}'")
            return json.loads(out)
        except:
            return {}
    
    def add_user_via_api(self, user_uuid, user_email, inbound_tag="vless-in"):
        """Add user via Xray gRPC API"""
        self.logger.log(f"Adding user via API: {user_email}")
        
        operation = {
            "tag": inbound_tag,
            "operation": {
                "type": "add",
                "value": {
                    "settings": {
                        "clients": [{
                            "id": user_uuid,
                            "email": user_email,
                            "flow": "xtls-rprx-vision"
                        }]
                    }
                }
            }
        }
        
        json_str = json.dumps(operation)
        cmd = f"echo '{json_str}' | xray api adi --server=127.0.0.1:8080"
        out, err, exit_code = self.ssh_conn.run_command(cmd)
        
        if exit_code == 0 and "no valid inbound" not in err.lower():
            self.logger.log(f"User {user_email} added successfully via API")
            return True
        else:
            self.logger.log(f"Failed to add user via API: {err}")
            return False
    
    def remove_user_via_api(self, user_email, inbound_tag="vless-in"):
        """Remove user via Xray gRPC API"""
        self.logger.log(f"Removing user via API: {user_email}")
        
        operation = {
            "tag": inbound_tag,
            "operation": {
                "type": "remove",
                "value": {
                    "settings": {
                        "clients": [{
                            "email": user_email
                        }]
                    }
                }
            }
        }
        
        json_str = json.dumps(operation)
        cmd = f"echo '{json_str}' | xray api adi --server=127.0.0.1:8080"
        out, err, exit_code = self.ssh_conn.run_command(cmd)
        
        if exit_code == 0 and "no valid inbound" not in err.lower():
            self.logger.log(f"User {user_email} removed successfully via API")
            return True
        else:
            self.logger.log(f"Failed to remove user via API: {err}")
            return False
    
    def get_user_stats_via_api(self, user_email):
        """Get user traffic stats via Xray API"""
        stats_cmd = f"xray api stats --name 'user>>>{user_email}>>>traffic>>>uplink' --server=127.0.0.1:8080"
        out, err, exit_code = self.ssh_conn.run_command(stats_cmd)
        
        if exit_code == 0:
            try:
                match = re.search(r'value:\s*(\d+)', out)
                if match:
                    return int(match.group(1))
            except:
                pass
        
        return 0
    
    def add_user(self, email=None, flow="xtls-rprx-vision"):
        """Add new user with API first, then fallback to graceful reload"""
        new_uuid = generate_uuid()
        users = self.load_users()
        
        if email:
            for user in users:
                if user.get("email") == email:
                    self.logger.log(f"User with email {email} already exists")
                    return None
        
        user_email = email or f"user_{new_uuid[:8]}@ravenvpn.local"
        
        new_user = {
            "uuid": new_uuid,
            "flow": flow,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "email": user_email
        }
        
        self.logger.log("Trying API method...")
        api_success = self.add_user_via_api(new_uuid, user_email)
        
        if api_success:
            users.append(new_user)
            self.save_users(users)
            self.logger.log("User added via API (no connection drops!)")
            return new_user
        else:
            self.logger.log("API failed, using graceful config reload...")
            users.append(new_user)
            self.save_users(users)
            
            config_manager = ConfigManager(self.ssh_conn, self.config)
            if config_manager.reload_config_graceful():
                self.logger.log("User added via graceful reload")
                return new_user
            else:
                users.remove(new_user)
                self.save_users(users)
                return None
    
    def remove_user(self, user_id):
        """Remove user with API first, then fallback to graceful reload"""
        users = self.load_users()
        
        user_to_remove = None
        for user in users:
            if user['uuid'] == user_id or user.get('email') == user_id:
                user_to_remove = user
                break
        
        if not user_to_remove:
            self.logger.log(f"User {user_id} not found")
            return False
        
        self.logger.log("Trying API method...")
        api_success = self.remove_user_via_api(user_to_remove['email'])
        
        if api_success:
            users = [u for u in users if u['uuid'] != user_id and u.get('email') != user_id]
            self.save_users(users)
            self.logger.log("User removed via API (no connection drops!)")
            return True
        else:
            self.logger.log("API failed, using graceful config reload...")
            users = [u for u in users if u['uuid'] != user_id and u.get('email') != user_id]
            self.save_users(users)
            
            config_manager = ConfigManager(self.ssh_conn, self.config)
            return config_manager.reload_config_graceful()
    
    def list_users(self):
        """Return list of users"""
        return self.load_users()
    
    def get_user_by_id(self, user_id):
        """Get user by UUID or email"""
        users = self.load_users()
        for user in users:
            if user['uuid'] == user_id or user.get('email') == user_id:
                return user
        return None


# ====== CONFIGURATION MANAGEMENT ======
class ConfigManager:
    """Manages Xray configuration"""
    def __init__(self, ssh_conn, config):
        self.ssh_conn = ssh_conn
        self.config = config
        self.logger = ssh_conn.logger
    
    def build_config(self, users_list, private_key, short_id):
        """Build Xray configuration JSON"""
        clients = []
        for user in users_list:
            client = {
                "id": user["uuid"],
                "flow": user.get("flow", "xtls-rprx-vision"),
                "email": user.get("email", f"user_{user['uuid'][:8]}@ravenvpn.local")
            }
            clients.append(client)
        
        return {
            "log": {"loglevel": "warning"},
            "api": {
                "tag": "api",
                "listen": "127.0.0.1:8080",
                "services": ["HandlerService", "StatsService"]
            },
            "stats": {},
            "inbounds": [
                {
                    "port": 443,
                    "protocol": "vless",
                    "tag": "vless-in",
                    "settings": {
                        "clients": clients,
                        "decryption": "none"
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "show": False,
                            "dest": f"{self.config.sni}:443",
                            "xver": 0,
                            "serverNames": [self.config.sni],
                            "privateKey": private_key,
                            "shortIds": [short_id]
                        }
                    }
                },
                {
                    "listen": "127.0.0.1",
                    "port": 10085,
                    "protocol": "dokodemo-door",
                    "settings": {
                        "address": "127.0.0.1"
                    },
                    "tag": "api"
                }
            ],
            "policy": {
                "levels": {
                    "0": {
                        "handshake": 4,
                        "connIdle": 300,
                        "uplinkOnly": 2,
                        "downlinkOnly": 5,
                        "statsUserUplink": True,
                        "statsUserDownlink": True
                    }
                }
            },
            "routing": {
                "rules": [
                    {
                        "type": "field",
                        "inboundTag": ["api"],
                        "outboundTag": "api"
                    }
                ]
            },
            "outbounds": [
                {"protocol": "freedom", "tag": "direct"},
                {"protocol": "blackhole", "tag": "blocked"}
            ]
        }
    
    def upload_config(self, config):
        """Upload configuration to server"""
        self.logger.log("Uploading config...")
        config_json = json.dumps(config, indent=2)
        
        self.ssh_conn.run_command("mkdir -p /usr/local/etc/xray")
        
        cmd = f"""cat << 'EOF' > {self.config.xray_config}
{config_json}
EOF"""
        self.ssh_conn.run_command(cmd)
    
    def reload_config_graceful(self):
        """Reload config gracefully using SIGHUP"""
        self.logger.log("Reloading config gracefully...")
        
        user_manager = UserManager(self.ssh_conn, self.config)
        users = user_manager.load_users()
        keys = user_manager.load_keys()
        
        if not keys:
            self.logger.log("ERROR: Keys not found!")
            return False
        
        config = self.build_config(users, keys["private_key"], keys["short_id"])
        self.upload_config(config)
        
        out, _, _ = self.ssh_conn.run_command("pkill -SIGHUP xray || killall -SIGHUP xray")
        time.sleep(1)
        
        out, _, exit_code = self.ssh_conn.run_command("pgrep xray")
        if exit_code == 0:
            self.logger.log("Xray reloaded gracefully")
            return True
        else:
            self.logger.log("SIGHUP failed, trying restart...")
            self.ssh_conn.run_command("systemctl restart xray")
            time.sleep(2)
            return True
    
    def start_xray(self):
        """Start Xray service"""
        self.logger.log("Starting Xray...")
        
        self.ssh_conn.run_command("systemctl daemon-reexec")
        self.ssh_conn.run_command("systemctl daemon-reload")
        self.ssh_conn.run_command("systemctl restart xray")
        self.ssh_conn.run_command("systemctl enable xray")
        
        time.sleep(3)
        
        self.logger.log("Checking Xray API...")
        out, _, _ = self.ssh_conn.run_command("xray api stats --server=127.0.0.1:8080 2>&1 || true")
        if "connection refused" in out.lower():
            self.logger.log("WARNING: API might not be ready yet")
        else:
            self.logger.log("Xray API is ready")


# ====== SYSTEM MANAGEMENT ======
class SystemManager:
    """Manages system configuration (firewall, etc)"""
    def __init__(self, ssh_conn):
        self.ssh_conn = ssh_conn
        self.logger = ssh_conn.logger
    
    def setup_firewall(self):
        """Configure UFW firewall"""
        self.logger.log("Configuring firewall...")
        
        self.ssh_conn.run_command("systemctl stop unattended-upgrades || true")
        self.ssh_conn.run_command("killall apt apt-get || true")
        self.ssh_conn.run_command("apt update -y")
        self.ssh_conn.run_command("apt install -y ufw")
        self.ssh_conn.run_command("ufw allow 22/tcp")
        self.ssh_conn.run_command("ufw allow 443/tcp")
        self.ssh_conn.run_command("ufw --force enable")


# ====== LINK GENERATION ======
class LinkGenerator:
    """Generates VLESS links for users"""
    def __init__(self, config):
        self.config = config
    
    def generate_user_link(self, user_uuid, public_key, short_id):
        """Generate VLESS link for a user"""
        return (f"vless://{user_uuid}@{self.config.server_ip}:443"
                f"?encryption=none&security=reality"
                f"&sni={self.config.sni}&fp=chrome"
                f"&pbk={public_key}"
                f"&sid={short_id}"
                f"&type=tcp&flow=xtls-rprx-vision")


# ====== MAIN DEPLOYMENT FUNCTION ======
def deploy(config, logger=None):
    """
    Main deployment function - can be imported and used in other projects
    
    Args:
        config: XrayConfig object with server details
        logger: Optional Logger instance
    
    Returns:
        dict: Deployment info including admin user and keys
    """
    if logger is None:
        logger = Logger()
    
    with SSHConnection(config, logger) as ssh_conn:
        installer = XrayInstaller(ssh_conn)
        installer.remove_xray()
        installer.install_xray()
        installer.wait_for_xray()
        
        private_key, public_key = generate_reality_keys()
        short_id = random_short_id()
        
        user_manager = UserManager(ssh_conn, config)
        user_manager.save_keys(private_key, public_key, short_id)
        
        admin_uuid = generate_uuid()
        admin_email = f"admin_{admin_uuid[:8]}@ravenvpn.local"
        admin_user = {
            "uuid": admin_uuid,
            "flow": "xtls-rprx-vision",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "email": admin_email
        }
        
        users = [admin_user]
        user_manager.save_users(users)
        
        config_manager = ConfigManager(ssh_conn, config)
        xray_config = config_manager.build_config(users, private_key, short_id)
        config_manager.upload_config(xray_config)
        
        system_manager = SystemManager(ssh_conn)
        system_manager.setup_firewall()
        config_manager.start_xray()
        
        time.sleep(2)
        logger.log("Testing API by adding a test user...")
        
        test_uuid = generate_uuid()
        test_email = "test@ravenvpn.local"
        if user_manager.add_user_via_api(test_uuid, test_email):
            logger.log("API test successful!")
            user_manager.remove_user_via_api(test_email)
        else:
            logger.log("API test failed, but Xray should still work")
        
        return {
            "server_ip": config.server_ip,
            "public_key": public_key,
            "short_id": short_id,
            "sni": config.sni,
            "admin_user": admin_user,
            "link": f"vless://{admin_uuid}@{config.server_ip}:443"
                    f"?encryption=none&security=reality"
                    f"&sni={config.sni}&fp=chrome"
                    f"&pbk={public_key}"
                    f"&sid={short_id}"
                    f"&type=tcp&flow=xtls-rprx-vision"
        }