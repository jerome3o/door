const host = "http://192.168.1.128:8000"
const lockerName = "closer"
const unlockerName = "opener"

function extend(name) {
  fetch(
    `${host}/api/extend`,
    {
      method: "POST",
      body: JSON.stringify({ name }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    }
  )
}

function retract(name) {
  fetch(
    `${host}/api/retract`,
    {
      method: "POST",
      body: JSON.stringify({ name }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    }
  )
}

function stop(name) {
  fetch(
    `${host}/api/stop`,
    {
      method: "POST",
      body: JSON.stringify({ name }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    }
  )
}

document.getElementById("extend1").onclick = () => extend(lockerName)
document.getElementById("retract1").onclick = () => retract(lockerName)
document.getElementById("stop1").onclick = () => stop(lockerName)

document.getElementById("extend2").onclick = () => extend(unlockerName)
document.getElementById("retract2").onclick = () => retract(unlockerName)
document.getElementById("stop2").onclick = () => stop(unlockerName)
