const host = ""


const message = document.getElementById("message")

function command(command) {
  return () => {
    fetch(
      `${host}/api/${command}`,
      {
        method: "POST",
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      }
    ).then(resp => resp.json()).then(json => {
      message.innerText = json.message
    })
  }
}

document.getElementById("unlockbutton").onclick = command("unlock")
document.getElementById("lockbutton").onclick = command("lock")
document.getElementById("stopbutton").onclick = command("stop")
document.getElementById("safebutton").onclick = command("safe")
