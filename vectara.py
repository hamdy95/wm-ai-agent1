import streamlit as st
import openai
from audiorecorder import audiorecorder
import tempfile
import toml

# Load API key from secrets.toml
openai_api_key = st.secrets["openai"]["api_key"]
client = openai.OpenAI(api_key=openai_api_key)

# Initialize session state variables
if 'selected_restaurant' not in st.session_state:
    st.session_state.selected_restaurant = None

# Function to transcribe audio
def transcribe_audio(audio_file):
    transcription = client.audio.transcriptions.create(
        model="whisper-1", 
        file=audio_file,
        language="ar"
    )
    return transcription.text

# System prompt for correcting transcriptions
def generate_corrected_transcript(temperature, system_prompt, transcription_text):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": transcription_text
            }
        ]
    )
    return response.choices[0].message.content

# Function to apply corrections to transcription
def apply_corrections(transcription_text):
    selected_restaurant = st.session_state.selected_restaurant
    menu = restaurant_menus[selected_restaurant]

    system_prompt = f"""
    You are a helpful assistant for correcting food orders. Correct any spelling errors in the transcribed text and make sure that the names of the following food items:
    . Only add necessary punctuation such as periods, commas, and capitalization, and use only the context provided.
    """
    
    corrected_text = generate_corrected_transcript(temperature=0, system_prompt=system_prompt, transcription_text=transcription_text)
    
    st.write("Corrected Transcription:")
    st.write(corrected_text)
    check_menu(corrected_text)

# Function to check if food is in the menu using GPT-4o
def check_menu(corrected_text):
    selected_restaurant = st.session_state.selected_restaurant
    menu = restaurant_menus[selected_restaurant]

    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {
                'role': 'system',
                'content': (
                    "You are tasked with checking if the ordered food is available in the restaurant's menu."
                )
            },
            {
                'role': 'user',
                'content': f"""
Restaurant Name: {selected_restaurant}

Menu:
{menu}

Customer Order: {corrected_text}

Check if the customer's order is available in the restaurant's menu. If the order is available, confirm it and display a message like 'Your order has been placed: [ordered items].' If the order is not on the menu, tell the user that the item is not available and ask them to select a restaurant again.
                """
            }
        ],
        max_tokens=4000
    )
    result = response.choices[0].message.content
    st.write(result)

# Restaurant selection
st.title("Restaurant Selection and Food Ordering App")

restaurant_menus = {
    "Pizza Palace": ["Pepperoni Pizza", "Margherita Pizza", "Cheese Pizza", "Veggie Pizza"],
    "Burger Shack": ["Cheeseburger", "Bacon Burger", "Veggie Burger", "Chicken Sandwich"],
    "Taco Town": ["Beef Taco", "Chicken Taco", "Fish Taco", "Vegetarian Taco"]
}

restaurant_list = list(restaurant_menus.keys())

st.write("Step 1: Select a restaurant")
selected_restaurant = st.selectbox("Choose a restaurant:", restaurant_list)

if selected_restaurant:
    st.session_state.selected_restaurant = selected_restaurant
    st.write(f"You selected: {selected_restaurant}")

# Step 2: Order food using voice or file upload
st.write("Step 2: Order your food using one of the methods below")

# Audio recording section
st.write("Or use your voice in real-time:")

# Audio recorder for real-time voice recording
audio = audiorecorder("Click to record", "Click to stop recording")

if len(audio) > 0:
    # To play audio in frontend:
    st.audio(audio.export().read())  

    # To save audio to a temporary file
    temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    audio.export(temp_audio_file.name, format="wav")

    with open(temp_audio_file.name, "rb") as audio_file:
        with st.spinner("Transcribing..."):
            transcription_text = transcribe_audio(audio_file)
        st.success("Transcription complete!")
        apply_corrections(transcription_text)
