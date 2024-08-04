// Set the host URL if needed
const host = "";

// Function to create command handlers
function createCommandHandler(command) {
  return () => {
    fetch(`${host}/api/${command}`, {
      method: "POST",
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
      .then(resp => resp.json())
      .then(json => {
        const message = document.getElementById("message");
        if (message) {
          message.innerText = json.message;
        }
      })
      .catch(error => {
        console.error('Error:', error);
      });
  };
}

// Create command functions
const unlock = createCommandHandler("unlock");
const lock = createCommandHandler("lock");
const stop = createCommandHandler("stop");
const safe = createCommandHandler("safe");

// Add event listeners when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
  const buttons = {
    "unlockbutton": unlock,
    "lockbutton": lock,
    "stopbutton": stop,
    "safebutton": safe
  };

  for (const [id, handler] of Object.entries(buttons)) {
    const button = document.getElementById(id);
    if (button) {
      button.addEventListener('click', handler);
    }
  }
});

console.log("Frontend loaded");
