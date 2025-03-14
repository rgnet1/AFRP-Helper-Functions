import os
import logging
import paramiko
from typing import Optional, Callable
from stat import S_ISREG
from utils.magazine.config import MagazineConfig

class ServerHandler:
    """Handles all server-related operations for magazine processing."""
    
    def __init__(self, config: MagazineConfig):
        """Initialize ServerHandler with configuration.
        
        Args:
            config: MagazineConfig instance containing necessary settings
        """
        self.config = config
        self.ssh = None
        self.sftp = None

    def connect(self) -> bool:
        """Establish SSH and SFTP connections to the server.
        
        First tries SSH key authentication, then falls back to password if available.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Try to load the default SSH key
            try:
                key_filename = os.path.expanduser('~/.ssh/id_rsa')
                print(f"Attempting SSH key authentication with {key_filename}...", flush=True)
                
                if os.path.exists(key_filename):
                    try:
                        self.ssh.connect(
                            self.config.server_ip,
                            username=self.config.server_user,
                            key_filename=key_filename,
                            look_for_keys=False,
                            allow_agent=False
                        )
                        print("Successfully connected using SSH key authentication", flush=True)
                        logging.info("Connected using SSH key authentication")
                        self.sftp = self.ssh.open_sftp()
                        return True
                    except paramiko.ssh_exception.AuthenticationException as e:
                        print(f"SSH key authentication failed: {str(e)}", flush=True)
                        logging.info(f"SSH key authentication failed: {str(e)}")
                else:
                    print(f"No SSH key found at {key_filename}", flush=True)
                    logging.info(f"No SSH key found at {key_filename}")

                # If we have a password, try password authentication
                if self.config.server_password:
                    print("Attempting password authentication...", flush=True)
                    try:
                        self.ssh.connect(
                            self.config.server_ip,
                            username=self.config.server_user,
                            password=self.config.server_password,
                            look_for_keys=False,
                            allow_agent=False
                        )
                        print("Successfully connected using password authentication", flush=True)
                        logging.info("Connected using password authentication")
                        self.sftp = self.ssh.open_sftp()
                        return True
                    except paramiko.ssh_exception.AuthenticationException as e:
                        print(f"Password authentication failed: {str(e)}", flush=True)
                        logging.error(f"Password authentication failed: {str(e)}")
                        return False
                else:
                    print("No password available for authentication", flush=True)
                    logging.error("No password available for authentication")
                    return False

            except paramiko.ssh_exception.AuthenticationException as e:
                print(f"Authentication failed: {str(e)}", flush=True)
                logging.error(f"Authentication failed: {str(e)}")
                return False
                    
        except paramiko.ssh_exception.NoValidConnectionsError:
            logging.error("Unable to connect to the server. Server might be down")
            print("Unable to connect to the server. Server might be down", flush=True)
            return False
        except Exception as e:
            logging.error(f"Failed to connect to server: {e}")
            print(f"Failed to connect to server: {e}", flush=True)
            return False

    def disconnect(self) -> None:
        """Close SSH and SFTP connections."""
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()
        self.sftp = None
        self.ssh = None

    def remote_path_exists(self, path: str) -> bool:
        """Check if a path exists on the remote server.
        
        Args:
            path: Remote path to check
            
        Returns:
            True if path exists, False otherwise
        """
        if not self.sftp:
            return False
            
        try:
            self.sftp.stat(path)
            return True
        except IOError:
            return False

    def remote_file_exists(self, path: str) -> bool:
        """Check if a specific file exists on the remote server.
        
        Args:
            path: Remote file path to check
            
        Returns:
            True if file exists, False otherwise
        """
        if not self.sftp:
            return False
            
        try:
            return S_ISREG(self.sftp.stat(path).st_mode)
        except IOError:
            return False

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """Upload a file to the remote server.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path on server
            progress_callback: Optional callback for upload progress
            
        Returns:
            True if upload successful, False otherwise
        """
        if not self.sftp:
            return False
            
        if not os.path.exists(local_path):
            logging.error(f"Local file {local_path} does not exist")
            print(f"Local file {local_path} does not exist", flush=True)
            return False

        try:
            # Upload file
            self.sftp.put(local_path, remote_path, callback=progress_callback)
            
            # Set permissions (760)
            self.sftp.chmod(remote_path, 0o760)
            
            # Set owner and group (using user and group IDs)
            rumz_uid = 1000
            user_gid = 100
            self.sftp.chown(remote_path, rumz_uid, user_gid)
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to upload {local_path} to {remote_path}: {e}")
            print(f"Failed to upload {local_path} to {remote_path}: {e}", flush=True)
            return False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
