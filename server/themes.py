import json
import re
import logging
from pathlib import Path
from pydantic import BaseModel
import anthropic
from fastapi import FastAPI, APIRouter
from fastapi.responses import HTMLResponse
from anthropic import AsyncAnthropic

from server.auth import User
from server.constants import STAGING_DIR, GENERATED_DIR, EXAMPLE_HTML_FILE

client = AsyncAnthropic()

router = APIRouter()

_logger = logging.getLogger(__name__)

with open(EXAMPLE_HTML_FILE) as f:
    EXAMPLE_HTML = f.read()


_SYSTEM_PROMPT = """\
This is a conversation between a user and Claude, a helpful AI assistant. The user is making a \
website to control a mechanism that locks and unlocks their apartment door, and would like help \
styling the website. The user will request a theme and some html for the website, and Claude will \
then respond with an update html file with the styles inlined.

When generating the html claude should:
* Use a lot of emojis
* Not include any images
* Respond with only the html content, enclosed in triple backticks
* Use animations and javascript where appropriate to make the website interesting
* Ensure the websites are mobile friendly
* Ensure that any existing scripts are loaded and still functional, specifically id "message"
* Make sure to add the theme name to the door controller website so the user knows what the theme is
* Try and incorporate the theme in the text on the buttons and title
* Try and use canvases, javascript, or other interactive elements to make the website more interesting
* Try an go above and beyond to make the website interesting, fun, novel, and engaging using your knowledge of web development and design
"""

_MESSAGE_TEMPLATE = """\
Please generate html for this website:
```
{html}
```

With the following theme: {theme}
{additional_information}

If it seems appropriate, try and use javascript and canvases (or three.js etc) to make it interesting

Then write out the full html file enclosed in triple backticks.
"""

_ADDITIONAL_INFO_TEMPLATE = """
Additional information:
{additional_information}
"""
class Theme(BaseModel):
    theme: str
    additional_information: str


async def generate_theme(theme_spec: Theme) -> str:
    theme = theme_spec.theme
    additional_information = theme_spec.additional_information

    additional_content = ""
    if additional_information != "":
        additional_content += _ADDITIONAL_INFO_TEMPLATE.format(
            additional_information=additional_information
        )

    content = _MESSAGE_TEMPLATE.format(
        html=EXAMPLE_HTML,
        theme=theme,
        additional_information=additional_content,
    )

    response = await client.messages.create(
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        model="claude-3-5-sonnet-20240620",
        messages=[{"role": "user", "content": content}],
    )

    assert response.content[0].type == "text"
    content = response.content[0].text

    # replace all ```html with just ```
    content = content.replace("```html", "```")

    if "```" not in content:
        raise ValueError("Response does not contain html content")

    # get content of ```
    content = content.split("```")[1]

    # make theme file name safe
    theme_fn = theme.replace(" ", "_").lower()
    theme_fn = re.sub(r"[^a-zA-Z0-9_]", "", theme_fn)
    theme_fn += ".html"
    theme_path = f"{STAGING_DIR}/{theme_fn}"

    # save to fe/generated
    with open(theme_path, "w") as f:
        f.write(content)

    return theme_fn



@router.post("/api/generate_theme")
async def generate_theme_endpoint(theme: Theme, user: User):
    _logger.info(f"{user} requested theme: {theme.theme}")
    theme_path = await generate_theme(theme)
    return {"message": "Theme generated", "theme_path": theme_path}


class AcceptThemeParams(BaseModel):
    theme_path: str


@router.post("/api/accept_theme")
async def accept_theme(accept_theme: AcceptThemeParams, user: User):
    _logger.info(f"{user} accepted theme: {accept_theme.theme_path}")
    theme_path = accept_theme.theme_path
    old_path = Path(f"{STAGING_DIR}/{theme_path}")
    new_path = Path(f"{GENERATED_DIR}/{theme_path}")

    if not old_path.exists():
        return {"message": "Theme not found"}

    i = 0
    while new_path.exists():
        i = i + 1
        new_path = new_path.with_name(f"{new_path.stem}_{i}{new_path.suffix}")

    old_path.rename(new_path)

    return {"message": "Theme accepted"}