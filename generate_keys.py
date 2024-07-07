import json
import secrets
import string
import os
from urllib.parse import urlparse

# List of names
names = ["ADD NAMES HERE"]


# Function to generate a random key
def generate_key(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# Generate keys for each name
keys = {name: generate_key() for name in names}

# Save keys to .keys.json file
with open(".keys.json", "w") as f:
    json.dump(keys, f, indent=2)

print("Keys have been saved to .keys.json")

# Get domain from environment variable
domain = os.getenv("DOOR_APP_DOMAIN")

if not domain:
    print("Error: DOOR_APP_DOMAIN environment variable is not set.")
    exit(1)

# Validate and format the domain
try:
    parsed_domain = urlparse(domain)
    if not parsed_domain.scheme:
        domain = f"https://{domain}"
    base_url = f"{domain}/?key="
except ValueError:
    print(
        f"Error: Invalid domain '{domain}'. Please set a valid domain in the DOOR_APP_DOMAIN environment variable."
    )
    exit(1)

# Print out links for each person
print("\nLinks to send out:")
for name, key in keys.items():
    link = f"{base_url}{key}"
    print(f"{name.capitalize()}: {link}")
