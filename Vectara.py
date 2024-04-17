import streamlit as st
from langchain.document_loaders import TextLoader  # From Langchain project
from langchain.text_splitter import CharacterTextSplitter  # From Langchain project
from langchain.vectorstores import Vectara  # From Langchain project
from langchain.llms import OpenAI  # From Langchain project
from langchain.chains import RetrievalQA  # From Langchain project
import os
from dotenv import load_dotenv  # From both projects (if used)
from clarifai.client.model import Model  # From Clarifai project
import base64

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
VECTARA_API_KEY = os.getenv('VECTARA_API_KEY')

def summarize_text(text_content):
    """
    This function extracts a brief summary of the text content (e.g., keywords or plant type).
    You can implement more sophisticated techniques here (e.g., named entity recognition).
    """
    # This is a basic example, replace with your desired summarization logic
    tokens = text_content.lower().split()
    keywords = [token for token in tokens if len(token) > 5]  # Filter out short words
    summary = " ".join(keywords[:5])  # Limit to top 5 keywords
    return summary


def langchain_func(file_name, question):
    """
    This function performs text-based question answering using Langchain.
    """
    loader = TextLoader(file_name, encoding='utf8')
    documents = loader.load()
    vectara = Vectara.from_documents(documents, embedding=None)
    qa = RetrievalQA.from_llm(llm=OpenAI(), retriever=vectara.as_retriever())
    answer = qa({'query': question})
    return answer


def diagnose_with_clarifai(image_bytes, file_content):
    # Clarifai model for plant diagnosis
    model_url = "https://clarifai.com/gcp/generate/models/gemini-pro-vision"
    clarifai_model = Model(url=model_url, pat="8866ee7a609c4b2992a931c11d46ac52")

    # Construct the prompt including the instructions for the model
    prompt = "As a plant doctor, mention the name of the plant and diagnose the plant issue based on the provided image and text."

    # Combine prompt, user query, and image bytes
    combined_data = prompt + " " + base64.b64encode(image_bytes).decode()

    # Predict using Clarifai model
    model_prediction = clarifai_model.predict_by_bytes(combined_data.encode(), input_type="text")
    
    # Check if model prediction outputs and data are available
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

    # File upload section
    file_content = st.file_uploader("Upload text file with plant information", type=['txt'])
    image_file = st.file_uploader("Upload image of the plant leaf (optional)", type=['jpg', 'png', 'jpeg'])



    # Question input and answer display
    question = st.text_input("Ask a question about the document:")
    if st.button("Ask"):
        if file_content is not None:
            answer = langchain_func(file_content.name, question)
            st.write("Answer:")
            st.write(answer)

    # Disease description display (based on image and potentially text content)
    if image_file is not None:
        image_bytes = image_file.read()
        if st.button("Diagnose Plant"):
          diagnose_with_clarifai(image_bytes, file_content)
       


if __name__ == "__main__":
    main()
