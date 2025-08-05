import os
import pyttsx3
import datetime
import wikipedia
import speech_recognition as sr
import webbrowser
import requests
import pywhatkit
import eel
from serpapi import GoogleSearch
import sqlite3
from bs4 import BeautifulSoup
import sys
import traceback
import google.generativeai as genai
from dotenv import load_dotenv

# ------------------ Load .env ------------------
# This loads environment variables from a .env file.
# Make sure you have a .env file in the same directory as this script
# with your API keys and email credentials.
load_dotenv()

# ------------------ Configuration ------------------
# Retrieve API keys and email credentials from environment variables.
# Replace default values with actual ones if not using .env
EMAIL_ADDRESS = os.getenv("MOBI_EMAIL", "your_email@gmail.com")
EMAIL_PASSWORD = os.getenv("MOBI_PASS", "your_app_password")
SERP_API_KEY = "feff1387f014839262ab3458321e6a69186186c44f223f959b531a0b7f81dfd7" # Updated with provided SerpAPI Key
GEMINI_API_KEY = "AIzaSyC1E2_BVGB4Zc5SFZ61hcdA8_88R1N8OHg" # Updated with provided Gemini API Key
DB_NAME = "assistant.db" # Database file name for history

# Initialize Eel - This points Eel to the web directory where index.html is located.
eel.init("www")

# ------------------ TTS Setup ------------------
# Initialize the text-to-speech engine (pyttsx3).
# Uses 'sapi5' for Windows, adjust for other OS if needed.
try:
    engine = pyttsx3.init('sapi5')
    voices = engine.getProperty('voices')
    # Set to a female voice (usually voices[1] for 'sapi5')
    engine.setProperty('voice', voices[1].id)
    engine.setProperty('rate', 175) # Adjust speech rate for better clarity
except Exception as e:
    print(f"TTS init error: {e}")
    engine = None # Set engine to None if initialization fails

def speak(text):
    """Converts text to speech and prints it to the console."""
    print(f"Mobi: {text}")
    try:
        if engine:
            engine.say(text)
            engine.runAndWait()
    except Exception as e:
        print(f"TTS speak error: {e}")

# ------------------ DB Init ------------------
def init_db():
    """Initializes the SQLite database and creates the history table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_input TEXT,
            assistant_response TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_history(user_input, assistant_response):
    """Saves user input and assistant response to the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO history (timestamp, user_input, assistant_response) VALUES (?, ?, ?)",
                   (timestamp, user_input, assistant_response))
    conn.commit()
    conn.close()

@eel.expose
def get_history():
    """Retrieves conversation history from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, user_input, assistant_response FROM history ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{'timestamp': row[0], 'user_input': row[1], 'assistant_response': row[2]} for row in rows]

@eel.expose
def clear_history():
    """Clears all conversation history from the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    conn.commit()
    conn.close()
    speak("History cleared.")
    return "History cleared."

# ------------------ Voice Input ------------------
def takecommand(max_attempts=2):
    """
    Listens for voice input from the microphone and converts it to text.
    Retries a specified number of times if recognition fails.
    """
    r = sr.Recognizer()
    for attempt in range(max_attempts):
        with sr.Microphone() as source:
            print("🎤 Listening...")
            r.adjust_for_ambient_noise(source, duration=1) # Adjust for ambient noise
            try:
                audio = r.listen(source, timeout=5) # Listen for up to 5 seconds
                print("Recognizing...")
                query = r.recognize_google(audio, language="en-in")
                print(f"User said: {query}")
                return query.lower()
            except sr.UnknownValueError:
                if attempt < max_attempts - 1:
                    speak("Sorry, I didn't catch that. Please repeat.")
                else:
                    speak("I am having trouble understanding. Please type your command.")
            except sr.RequestError as e:
                speak(f"Could not request results from Google Speech Recognition service; {e}")
            except Exception as e:
                print(f"Speech recognition error: {e}")
    return "none" # Return "none" if all attempts fail

# ------------------ SerpAPI Search ------------------
def search_serpapi(query):
    """
    Performs a Google search using SerpAPI and returns the most relevant snippet.
    Requires a valid SERP_API_KEY.
    """
    if not SERP_API_KEY or SERP_API_KEY == "YOUR_SERP_API_KEY":
        return "SerpAPI key is not configured. Please set SERP_API_KEY in your .env file."

    params = {"engine": "google", "q": query, "api_key": SERP_API_KEY}
    try:
        search = GoogleSearch(params)
        results = search.get_dict()

        if "answer_box" in results:
            box = results["answer_box"]
            return box.get("answer") or box.get("snippet") or " ".join(box.get("highlighted_words", []))
        if results.get("organic_results"):
            return results["organic_results"][0].get("snippet", "No result found.")
        return "Sorry, I couldn't find anything specific with SerpAPI."
    except Exception as e:
        return f"SerpAPI Error: {e}"

# ------------------ Gemini AI ------------------
# Helper function to list available Gemini models (for debugging)
def list_gemini_models():
    """Lists available Gemini models that support generateContent."""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("Available Gemini models supporting 'generateContent':")
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

def query_gemini(prompt):
    genai.configure(api_key=GEMINI_API_KEY)
    # Print available models for debugging
    available = [m.name for m in genai.list_models()]
    print("Available models:", available)
    model_name = None
    for name in available:
        if "2.5-pro" in name or "1.5-pro" in name or "2.5-flash" in name:
            model_name = name
            break
    if not model_name:
        return "Gemini AI Error: No supported model available for your key."

    try:
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        return f"Gemini AI Error: {e}"


# ------------------ Cricket Score ------------------
def get_cricket_score():
    """Fetches live cricket scores from Google search results."""
    try:
        url = "https://www.google.com/search?q=cricket+score"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        # Attempt to find specific elements for cricket scores
        score_card_div = soup.find("div", class_="imso_mh__l-sf-sg") # Common class for score summary
        if score_card_div:
            # Extract relevant text from the score card
            score_text = score_card_div.get_text(separator=" ", strip=True)
            result = f"Live Cricket Score: {score_text}"
            speak(result)
            eel.displayResult(result)
            return result
        else:
            # Fallback if specific class not found
            match_info = soup.find("div", class_="BNeawe deIvCb AP7Wnd")
            score_info = soup.find("div", class_="BNeawe iBp4i AP7Wnd")
            if match_info and score_info:
                result = f"{match_info.text.strip()} - {score_info.text.strip()}"
                speak(result)
                eel.displayResult(result)
                return result
            else:
                msg = "No live cricket match data found at the moment."
                speak(msg)
                eel.displayResult(msg)
                return msg
    except Exception as e:
        msg = f"Error fetching cricket score: {e}"
        speak(msg)
        eel.displayResult(msg)
        return msg

# ------------------ Query Handler ------------------
def handle_query(query):
    """
    Processes the user's query and directs it to the appropriate function.
    This is the core logic of the assistant.
    """
    if not query or query == "none":
        return "No command received"

    query = query.lower()

    if "president of india" in query:
        answer = "The current President of India is Droupadi Murmu."
        speak(answer)
        eel.displayResult(answer)
        return answer

    elif 'open stackoverflow' in query:
        webbrowser.open("https://stackoverflow.com")
        speak("Opened Stack Overflow")
        eel.displayResult("Opened Stack Overflow")
        return "Opened Stack Overflow"

    elif 'time' in query:
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The time is {now}")
        eel.displayResult(now)
        return now

    elif 'open youtube' in query:
        webbrowser.open("https://youtube.com")
        speak("Opening YouTube")
        eel.displayResult("Opened YouTube")
        return "Opened YouTube"

    elif 'open google' in query:
        webbrowser.open("https://google.com")
        speak("Opening Google")
        eel.displayResult("Opened Google")
        return "Opened Google"

    elif 'open chat gpt' in query or 'open chatgpt' in query:
        webbrowser.open("https://chat.openai.com")
        speak("Opening ChatGPT")
        eel.displayResult("Opened ChatGPT")
        return "Opened ChatGPT"

    elif 'whatsapp' in query and 'message' in query:
        try:
            speak("To which number do you want to send the message? Please say the full number including country code if not Indian.")
            number = takecommand().replace("plus", "+").replace(" ", "").replace("-", "")
            if not number.startswith("+"):
                # Assume Indian number if no country code is given and it's 10 digits
                if len(number) == 10:
                    full_number = f"+91{number}"
                else:
                    msg = "Invalid number format. Please include country code or provide a 10-digit Indian number."
                    speak(msg)
                    eel.displayResult(msg)
                    return msg
            else:
                full_number = number

            if len(full_number) < 10: # Basic validation for number length
                msg = "Invalid number format. Number too short."
                speak(msg)
                eel.displayResult(msg)
                return msg

            speak("What is the message?")
            message = takecommand()
            if message == "none":
                msg = "No message entered."
                speak(msg)
                eel.displayResult(msg)
                return msg

            # pywhatkit.sendwhatmsg_instantly opens a browser tab and sends the message
            # wait_time is in seconds before closing the tab
            pywhatkit.sendwhatmsg_instantly(full_number, message, wait_time=15, tab_close=True, close_time=5)
            msg = "Message sent successfully."
            speak(msg)
            eel.displayResult(msg)
            return msg
        except Exception as e:
            msg = f"Error sending WhatsApp message: {e}. Make sure WhatsApp Web is logged in on your browser."
            speak(msg)
            eel.displayResult(msg)
            return msg

    elif 'cricket' in query:
        return get_cricket_score()

    elif "who made you" in query or "your creator" in query:
        answer = "I was created by Monu Maurya, a passionate Python developer."
        speak(answer)
        eel.displayResult(answer)
        return answer

    elif 'wikipedia' in query:
        try:
            topic = query.replace("wikipedia", "").replace("search", "").replace("on", "").strip()
            if not topic:
                speak("What would you like to search on Wikipedia?")
                topic = takecommand().strip()
                if not topic or topic == "none":
                    msg = "No topic provided for Wikipedia search."
                    speak(msg)
                    eel.displayResult(msg)
                    return msg

            speak(f"Searching Wikipedia for {topic}...")
            results = wikipedia.summary(topic, sentences=2)
            speak("According to Wikipedia...")
            speak(results)
            eel.displayResult(results)
            return results
        except wikipedia.exceptions.DisambiguationError as e:
            msg = f"That term is ambiguous. Possible options: {', '.join(e.options[:5])}. Please try being more specific."
            speak(msg)
            eel.displayResult(msg)
            return msg
        except wikipedia.exceptions.PageError:
            msg = "Sorry, I couldn't find any Wikipedia page for that. Please try a different query."
            speak(msg)
            eel.displayResult(msg)
            return msg
        except Exception as e:
            msg = f"Wikipedia error: {e}"
            speak(msg)
            eel.displayResult(msg)
            return msg

    elif "how many" in query or "who is" in query or "what is" in query or "when" in query or "how" in query or "where is" in query:
        # Prioritize SerpAPI for factual questions that require up-to-date info
        try:
            speak(f"Searching online for {query}...")
            result = search_serpapi(query)
            speak(result)
            eel.displayResult(result)
            return result
        except Exception as e:
            msg = f"Search error: {e}"
            speak(msg)
            eel.displayResult(msg)
            return msg

    # Fallback to Gemini AI for general conversational queries or if other commands don't match
    speak("Let me think...")
    result = query_gemini(query)
    speak(result)
    eel.displayResult(result)
    return result

# ------------------ Eel Interface ------------------
@eel.expose
def start_voice_assistant():
    """
    Exposed to JavaScript to initiate voice command listening and processing.
    Returns the user's query and Mobi's response.
    """
    speak("Listening now...")
    query = takecommand()
    if query == "none":
        eel.displayResult("❌ I didn't catch that. Please try again.")
        return {"query": "❌ I didn't catch that.", "result": ""}

    result = handle_query(query)
    save_history(query, result)

    return {
        "query": f"✅ You said: {query}",
        "result": result
    }

@eel.expose
def process_text_command(command_text):
    """
    Exposed to JavaScript to process text commands from the UI.
    """
    if not command_text:
        eel.displayResult("Please enter a command.")
        return {"query": "No command entered.", "result": ""}

    query = command_text.lower().strip()
    print(f"User (text): {query}")

    result = handle_query(query)
    save_history(query, result)

    return {
        "query": f"✅ You typed: {command_text}",
        "result": result
    }

# ------------------ Global Error Catcher ------------------
def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to log uncaught exceptions."""
    if not issubclass(exc_type, KeyboardInterrupt):
        print("Uncaught exception:", "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        speak("Oops! Something went wrong. Please check the console for details.")

sys.excepthook = handle_exception

# ------------------ App Start ------------------
# ------------------ App Start ------------------
if __name__ == "__main__":
    init_db() # Initialize the database
    # Uncomment the line below to list available Gemini models for debugging
    list_gemini_models() # <--- UNCOMMENT THIS LINE
    speak("Hello, I am Mobi, your virtual assistant. How can I help you today?")
    eel.start("index.html", size=(700, 600), mode='chrome', port=8000)