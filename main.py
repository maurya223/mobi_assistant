import eel
from virtual_assistant.mobicore import speak, takecommand, handle_query

eel.init("www")  # frontend folder

@eel.expose
def start_voice_assistant():
    speak("Listening now...")
    query = takecommand()
    if query == "none":
        return {
            "query": "❌ I didn't catch that.",
            "result": ""
        }

    result = handle_query(query)
    return {
        "query": f"✅ You said: {query}",
        "result": result
    }

if __name__ == "__main__":
    speak("Launching Mobi Virtual Assistant")
    try:
        eel.start("index.html", size=(700, 500), mode="chrome", cmdline_args=["--app=http://localhost"])
    except EnvironmentError:
        eel.start("index.html", size=(700, 500))  # fallback if Chrome not found
