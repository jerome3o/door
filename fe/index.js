const host = "http://192.168.1.128:8000"

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
    )
  }
}

document.getElementById("unlockbutton").onclick = command("unlock")
document.getElementById("lockbutton").onclick = command("lock")
document.getElementById("stopbutton").onclick = command("stop")
document.getElementById("safebutton").onclick = command("safe")
