import streamlit as st
import pdfplumber
import os
from dotenv import load_dotenv
import requests
import re

# --- Load environment variables ---
load_dotenv()

# --- Page Setup ---
st.set_page_config(page_title="Resume Scorer Pro", layout="wide")
st.title("🚀 Resume Scorer Pro")

# --- Session State Initialization ---
if 'analysis_done' not in st.session_state:
    st.session_state.update({
        'analysis_done': False,
        'resume_text': "",
        'analysis_result': {}
    })

# --- Helper: Shorten Text for LLM Input ---
def shorten_text(text, max_length=700):
    if len(text) <= max_length:
        return text
    keywords = ["experience", "skills", "education", "project", "achievement"]
    sections = []
    for keyword in keywords:
        idx = text.lower().find(keyword)
        if idx != -1:
            start = max(0, idx - 50)
            end = min(len(text), idx + len(keyword) + 150)
            sections.append(text[start:end])
    result = "...".join(sections)[:max_length]
    return result if result else text[:max_length]

# --- Extract Text from Resume PDF ---
def extract_resume_text(file):
    try:
        with pdfplumber.open(file) as pdf:
            full_text = "\n".join(page.extract_text() for page in pdf.pages[:3] if page.extract_text())
            short_text = shorten_text(full_text, 1000)
            st.session_state.resume_text = short_text
            return short_text
    except Exception as e:
        return f"PDF Error: {str(e)}"

# --- Parse GPT Output ---
def parse_analysis_output(text):
    result = {
        "score": "N/A",
        "missing_skills": ["Not specified"],
        "suggestion": []
    }

    # --- Extract score using regex ---
    score_match = re.search(r"\b(\d{1,3})\b\s*(?:/100|out of 100)?", text)
    if score_match:
        score = int(score_match.group(1))
        if 0 <= score <= 100:
            result["score"] = str(score)

    # --- Extract missing skills ---
    skill_keywords = ["missing skills", "skills missing", "lacking skills", "required skills", "skill gaps"]
    for line in text.split('\n'):
        if any(keyword in line.lower() for keyword in skill_keywords):
            skills_line = line.split(':')[-1].strip()
            skills = [s.strip(" .•-") for s in re.split(r",|and", skills_line)]
            result["missing_skills"] = skills[:3]
            break

    # --- Extract multiple suggestions ---
    suggestion_section = False
    suggestions = []
    for line in text.split('\n'):
        if any(k in line.lower() for k in ["suggestion", "recommend", "advice", "improvement"]):
            suggestion_section = True
        elif suggestion_section and (line.strip().startswith("-") or line.strip().startswith("•")):
            suggestions.append(line.strip("-• ").split('.')[0])
        elif suggestion_section and not line.strip():
            break

    result["suggestion"] = suggestions[:5] if suggestions else ["No suggestions found."]
    return result

# --- Use GPT-3.5 via OpenRouter ---
def analyze_with_openrouter(jd, resume):
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        return {"error": "Missing OPENROUTER_API_KEY in .env file"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    prompt = f"""
You are a resume screening assistant.

Job Description:
{jd}

Resume:
{resume}

Now analyze:
- Give a score out of 100 for compatibility.
- List two missing skills (comma-separated).
- Suggest five improvements as a bullet list.
"""

    data = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )

        if response.status_code == 200:
            output = response.json()["choices"][0]["message"]["content"]
            return parse_analysis_output(output)
        else:
            return {"error": f"OpenRouter Error: {response.text}", "prompt": prompt}
    except Exception as e:
        return {"error": f"Request failed: {e}"}

# --- Main App Logic ---
def main():
    st.markdown("Upload your resume and paste a job description to get a compatibility analysis.")

    job_desc = st.text_area("📜 Job Description", height=100, placeholder="Enter job description (1-2 sentences)", max_chars=300)
    resume_file = st.file_uploader("📄 Upload Resume (PDF, max 3 pages)", type=["pdf"])

    if st.button("Analyze Resume"):
        if not job_desc or not resume_file:
            st.error("Please provide both a job description and a resume.")
        else:
            with st.spinner("Analyzing with GPT-3.5..."):
                resume_text = extract_resume_text(resume_file)
                if "Error" in resume_text:
                    st.error(resume_text)
                else:
                    result = analyze_with_openrouter(job_desc, resume_text)
                    st.session_state.analysis_result = result
                    st.session_state.analysis_done = True

    if st.session_state.analysis_done:
        st.divider()
        st.subheader("📊 Analysis Results")
        result = st.session_state.analysis_result

        if "error" in result:
            st.error(result["error"])
            with st.expander("🔍 View Debug Info"):
                st.code(result.get("prompt", "No prompt available"))
            st.markdown("""
            **Tips to fix:**
            - Make inputs shorter
            - Check API key in `.env`
            - Try again later
            """)
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Compatibility Score", result.get("score", "N/A"))
                st.write("**Missing Skills:**")
                for skill in result.get("missing_skills", []):
                    st.write(f"- {skill}")
            with col2:
                st.write("**Improvement Suggestions:**")
                suggestions = result.get("suggestion", [])
                if isinstance(suggestions, list):
                    for s in suggestions:
                        st.write(f"- {s}")
                else:
                    st.info(suggestions)
                with st.expander("📟 View Processed Resume Text"):
                    st.text(st.session_state.resume_text[:700] + "...")

if __name__ == "__main__":
    main()
