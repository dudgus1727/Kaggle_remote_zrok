import urllib.request
import os
import sys
import json
import subprocess
import platform
import shutil

class Zrok:
    # zrok v2 installs its binary as `zrok2` (Homebrew still names it `zrok`)
    BINARY_CANDIDATES = ("zrok2", "zrok")
    INSTALL_SCRIPT_URL = "https://get.openziti.io/install.bash"

    def __init__(self, token: str, name: str = None):
        """Initialize Zrok instance with API token and optional environment name.
        
        Args:
            token (str): Zrok API token for authentication
            name (str, optional): Name/description for the zrok environment. Defaults to None.
        """
        if token.startswith('<') and token.endswith('>'):
            raise ValueError("Please provide an actual your zrok token")
        
        self.token = token
        self.name = name
        self.base_url = "https://api-v2.zrok.io/api/v2"

    def get_env(self):
        """Get overview of all zrok environments using HTTP API.

        This method uses HTTP API to retrieve environments even when zrok enable command fails.
        
        Returns:
            dict: Overview data containing environments information
            None: If the API call fails or no environments exist
        """
        req = urllib.request.Request(
            url=f"{self.base_url}/overview",
            headers={"x-token": self.token},
        )

        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            data = response.read().decode('utf-8')
            data = json.loads(data) 

        if status != 200:
            print(f"Error: {status}")
            raise Exception("zrok API overview error")
        
        return data['environments']

    def find_env(self, name: str):
        """Find a specific environment by its name.
        
        Args:
            name (str): Name/description of the environment to find (case-insensitive)
        
        Returns:
            dict: Environment information if found
            None: If no environment matches the given name
        """
        overview = self.get_env()
        if overview is None:
            return None

        for item in overview:
            env = item["environment"]
            if env["description"].lower() == name.lower():
                return item
            
        return None

    def delete_environment(self, zId: str):
        """Delete a zrok environment by its ID.
        
        Args:
            zid (str): The environment ID to delete
        
        Returns:
            bool: True if the environment was successfully deleted, False otherwise
        """
        headers = {
            "x-token": self.token,
            "Accept": "*/*",
            "Content-Type": "application/zrok.v1+json"
        }
        payload = {
            "identity": zId
        }
        
        data_bytes = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(f"{self.base_url}/disable", headers=headers, data=data_bytes, method="POST")
        with urllib.request.urlopen(req) as response:
            status = response.getcode()

        if status != 200:
            raise Exception("Failed to delete environment")

        return True

    def enable(self, name: str = None):
        """Enable zrok with the specified environment name.
        
        This method runs the 'zrok enable' command with the provided token and
        environment name. It will create a new environment if one doesn't exist.
        
        Args:
            name (str, optional): Name/description for the zrok environment.
                                 If not provided, uses the name from initialization.
            
        Raises:
            RuntimeError: If enable command fails
        """
        env_name = name if name is not None else self.name
        if env_name is None:
            raise ValueError("Environment name must be provided either during initialization or when calling enable()")
        
        subprocess.run([Zrok.binary(), "enable", self.token, "-d", env_name, "--headless"], check=True)

    def disable(self, name: str = None):
        """Disable zrok.
        
        This function executes the zrok disable command to delete the environment stored in the local file ~/.zrok2/environment.json,
        and additionally removes any environments that could not be deleted through HTTP communication.
        
        Args:
            name (str, optional): Name/description for the zrok environment.
                                If not provided, uses the name from initialization.
        """
        env_name = name if name is not None else self.name

        # Delete the ~/.zrok2/environment.json file
        try:
            subprocess.run([Zrok.binary(), "disable"], check=True)
        except Exception as e:
            print(e)
            print("zrok already disable")

        # Delete environment via HTTP communication even if zrok is not enabled
        env = self.find_env(env_name)
        if env is not None:
            self.delete_environment(env['environment']['zId'])

    @staticmethod
    def binary():
        """Return the name of the installed zrok v2 executable.

        Returns:
            str: `zrok2` or `zrok` (whichever is a v2 build)

        Raises:
            FileNotFoundError: If no zrok v2 executable is found
        """
        for name in Zrok.BINARY_CANDIDATES:
            if shutil.which(name) is None:
                continue
            try:
                result = subprocess.run([name, "version"], capture_output=True, text=True)
            except OSError:
                continue
            if "v2." in result.stdout + result.stderr:
                return name
        raise FileNotFoundError("zrok v2 is not installed")

    @staticmethod
    def install():
        """Install zrok v2 using the official OpenZiti install script.

        Runs: curl -sSf https://get.openziti.io/install.bash | sudo bash -s zrok2
        """
        if platform.system() != 'Linux':
            raise Exception("This script only works on Linux. For other operating systems, \
                            please install zrok2 manually following the instructions at https://docs.zrok.io/docs/guides/install/")

        print("Installing zrok2")
        sudo = "" if os.geteuid() == 0 else "sudo "
        subprocess.run(f"curl -sSf {Zrok.INSTALL_SCRIPT_URL} | {sudo}bash -s zrok2", shell=True, check=True)

        if not Zrok.is_installed():
            raise RuntimeError("Failed to verify zrok2 installation")

        print("Successfully installed zrok2")

    @staticmethod
    def is_installed():
        """Check if zrok v2 is installed and accessible.

        Returns:
            bool: True if a zrok v2 executable is found, False otherwise
        """
        try:
            Zrok.binary()
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def is_enabled() -> bool:
        """Check if zrok is enabled.
        
        Returns:
            bool: True if zrok is enabled (Account Token and Ziti Identity are set), False otherwise
        """
        try:
            result = subprocess.run(
                [Zrok.binary(), "status"],
                capture_output=True,
                text=True,
                check=True
            )
            # Check if both Account Token and Ziti Identity are set
            return "Account Token  <<SET>>" in result.stdout and "Ziti Identity  <<SET>>" in result.stdout
        except subprocess.CalledProcessError:
            return False
        except FileNotFoundError:
            return False

  