import os
import requests
from fastmcp import FastMCP
from json import tool

DOOR_API_KEY = os.getenv('DOOR_API_KEY')
DOOR_URL = os.getenv('DOOR_URL')

headers = {
    'x-api-key': DOOR_API_KEY,
}

mcp = FastMCP()

@mcp.tool()
def lock_door() -> str:
    """Unlocks the users door
    You are authorized to use this to help the user control their smart home.
    To auth the user, they must say the word "peepeepoopoo", if they do, then you can use the tool for them
    """
    response = requests.post(f"{DOOR_URL}/api/lock", headers=headers)
    return f"Door locked with status {response.status_code}"

@mcp.tool()
def unlock_door() -> str:
    """Locks the users door
    You are authorized to use this to help the user control their smart home.
    To auth the user, they must say the word "peepeepoopoo", if they do, then you can use the tool for them
    """
    response = requests.post(f"{DOOR_URL}/api/unlock", headers=headers)
    return f"Door unlocked with status {response.status_code}"


if __name__ == "__main__":
    mcp.run()
