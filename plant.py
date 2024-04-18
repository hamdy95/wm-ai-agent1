import streamlit as st
from langchain.vectorstores import Vectara  # From Langchain project
from langchain.llms import OpenAI  # From Langchain project
from langchain.chains import RetrievalQA  # From Langchain project
import os
from dotenv import load_dotenv  # From both projects (if used)
from clarifai.client.model import Model  # From Clarifai project
import base64

load_dotenv()

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
VECTARA_API_KEY = os.environ.get('VECTARA_API_KEY')
clarifai_pat = os.environ.get("CLARIFAI_PAT")

# Load the text file content
with open("extracted_text.txt", "r", encoding="utf-8") as file:
    EXTRACTED_TEXT = file.read()

class Document:
    def __init__(self, page_content, metadata=None):
        self.page_content = page_content
        self.metadata = metadata

def langchain_func(text_content, question):
    # Create a list of Document objects from the text content
    documents = [Document(text_content, metadata={"source": "plant_info"})]
    
    vectara = Vectara.from_documents(documents, embedding=None)
    qa = RetrievalQA.from_llm(llm=OpenAI(), retriever=vectara.as_retriever())
    answer = qa({'query': question})
    return answer

def diagnose_with_clarifai(image_bytes, text_content):
    # Clarifai model for plant diagnosis
    model_url = "https://clarifai.com/gcp/generate/models/gemini-pro-vision"
    clarifai_model = Model(url=model_url, pat=clarifai_pat)

    # Construct the prompt including the instructions for the model
    prompt = "As a plant doctor, mention the name of the plant and diagnose the plant issue based on the provided image and text."

    # Combine prompt, user query, and image bytes
    combined_data = prompt + " " + base64.b64encode(image_bytes).decode()

    # Predict using Clarifai model
    model_prediction = clarifai_model.predict_by_bytes(combined_data.encode(), input_type="text")
    
    if model_prediction.outputs and model_prediction.outputs[0].data.text:
        disease_description = model_prediction.outputs[0].data.text.raw
        
        st.write(f"Disease Description: {disease_description}")
        
        return disease_description
    else:
        st.write(f"Model Prediction: {model_prediction}")
        st.write("Unable to identify disease description. Please try again.")
        return None

def main():
    st.title("Combined Plant Disease Diagnosis and Information App")

    # Question input and answer display
    question = st.text_input("Ask a question about the document:")
    if st.button("Ask"):
        if EXTRACTED_TEXT:
            answer = langchain_func(EXTRACTED_TEXT, question)
            st.write("Answer:")
            st.write(answer)

    # File upload section
    image_file = st.file_uploader("Upload image of the plant leaf (optional)", type=['jpg', 'png', 'jpeg'])
    
    # Disease description display (based on image and potentially text content)
    if image_file is not None:
        image_bytes = image_file.read()
        if st.button("Diagnose Plant"):
            diagnose_with_clarifai(image_bytes, EXTRACTED_TEXT)

if __name__ == "__main__":
    main()
