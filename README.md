# Very Cool Door Control

This is a webserver designed to run on a RPi with some linear actuators to unlock/lock a door.

## Setup

### Environment

```sh
python3 -m venv venv
. ./venv/bin/activate
pip install -r requirements.txt
```

Sometimes RPi's will need you to install with apt instead, just run:

```sh
sudo apt install python3-XXX
```

Where `XXX` is the package name that you end up missing.

### Folders and keys

You'll need to provide access keys for people you want to use the app

#### Automatic

Edit generate_keys.py with names of your friends

Then run it:

```sh
DOOR_APP_DOMAIN=yourdomain.com python generate_keys.py
```

And it will make the `.keys.json` file needed

#### Manual

Make a `.keys.json` file and add entries like:

```json
{
  "friend_1": "secret_key_1",
  "friend_2": "secret_key_2"
}
```

### Run the server

Run the server from project root dir:

```sh
uvicorn app:main
```
