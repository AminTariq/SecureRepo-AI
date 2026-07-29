# 🚀 [Tips Hindawi](https://www.tipshindawi.com/) Challenge (June–July) 2026

> 🏆 This repository is my official submission for the [**Tips Hindawi**](https://www.tipshindawi.com/) **Challenge (June–July 2026)**.

## 👤 Participant

| Field            | Value                                |
| ---------------- | ------------------------------------ |
| Full Name        | **Amin Tarig Amin Abbas**            |
| Project Name     | **SecureRepo AI**                    |
| GitHub Username  | **AminTariq**                         |
| Challenge Batch  | June–July 2026                       |
| Training Program | Large Language Models (LLMs) Program |
| Organization     | [**Edrak for Ai**](https://edrak4ai.com/en) |

---

# 📖 Project Overview

**SecureRepo AI** is an AI-powered first-pass security reviewer for public Python GitHub repositories. It combines Bandit static-analysis evidence, FAISS RAG guidance, and a fine-tuned open-source LLM to produce clear, AI-supported findings and suggested fixes.

I saw security risks growing alongside vibe coding, so I wanted to solve the problem cleanly. I first fine-tuned **Qwen3-4B-Instruct-2507** with Unsloth and QLoRA on [**1,200 curated synthetic Python security examples**](dataset/securerepo_train.jsonl)—800 vulnerable and 400 safe—then uploaded the trained LoRA adapter to [**Hugging Face**](https://huggingface.co/AminTariq/securerepo-qwen3-4b-lora). I added FAISS RAG and Bandit in Kaggle, schema-validated the generated reports with Pydantic, exposed the backend through FastAPI and ngrok, and connected it to a Streamlit frontend.

```text
GitHub URL → Bandit → FAISS RAG → Fine-tuned Qwen → Pydantic → Streamlit
```

SecureRepo AI is designed as a practical first-pass review and learning tool, not a replacement for a professional security audit.

---

# ✨ Features

* Scans public Python GitHub repositories without executing their code
* Combines Bandit, RAG, and a fine-tuned open-source LLM
* Uses a LoRA adapter trained on 1,200 curated synthetic security examples
* Produces AI-supported findings with severity, confidence, CWE, OWASP, evidence, and suggested fixes
* Streams live progress to Streamlit, saves scan history, and exports JSON reports

---

# 🛠️ Technologies Used

| Area | Technologies |
| ---- | ------------ |
| Model | Qwen3-4B-Instruct-2507, Unsloth, QLoRA, PEFT |
| Security | Bandit, CWE, OWASP |
| RAG | FAISS, LangChain, Sentence Transformers |
| Validation | Pydantic schema validation |
| Backend | Kaggle GPU, FastAPI, Uvicorn, ngrok |
| Frontend | Streamlit, Requests, SQLite |

---

# ⚙️ Installation

### 1. Start the Kaggle backend

1. Open `notebooks/SecureRepo_AI_Kaggle_Backend.ipynb` in Kaggle.
2. Enable a GPU and Internet access.
3. Add `NGROK_AUTHTOKEN` to Kaggle Secrets.
4. Run all nine notebook blocks.
5. Keep Kaggle running and copy the backend URL and API key printed by the final block.

### 2. Run the Streamlit frontend

Open PowerShell in the project folder:

```powershell
git clone https://github.com/AminTariq/SecureRepo-AI.git
cd SecureRepo-AI

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add:

```toml
SECUREREPO_BACKEND_URL = "YOUR_KAGGLE_NGROK_URL"
SECUREREPO_API_KEY = "YOUR_SECUREREPO_API_KEY"
```

Then start the app:

```powershell
python -m streamlit run app.py
```

> Never upload `.streamlit/secrets.toml`, API keys, ngrok tokens, or active tunnel URLs to GitHub.

---

# 🚀 Usage

1. Keep the Kaggle backend running and open the local Streamlit app.
2. Paste a public GitHub repository URL and choose how many Python files to review.
3. Start the scan and review the streamed findings.
4. Download the final JSON report if needed.

---

# 📸 Demo

The screenshots below show the complete flow—from opening the workspace to reviewing a schema-validated security report—using the public [Vulpy test repository](https://github.com/fportantier/vulpy).

![SecureRepo AI schema-validated security report](assets/screenshots/11-validated-security-report.png)

<p align="center"><sub>Schema-validated repository report with a risk score, severity summary, AI-supported findings, and downloadable JSON output.</sub></p>

<details>
<summary><strong>1. Access and workspace overview</strong></summary>
<br>

<table>
  <tr>
    <td align="center"><strong>Demo authentication</strong></td>
    <td align="center"><strong>Repository overview</strong></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/01-login.png" alt="SecureRepo AI demo login screen"></td>
    <td><img src="assets/screenshots/02-repository-overview.png" alt="SecureRepo AI repository overview dashboard"></td>
  </tr>
</table>

</details>

<details>
<summary><strong>2. Repository scan and live AI analysis</strong></summary>
<br>

<table>
  <tr>
    <td align="center"><strong>Configure a public repository scan</strong></td>
    <td align="center"><strong>Stream AI-supported evidence</strong></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/03-new-repository-scan.png" alt="Configure a new GitHub repository scan"></td>
    <td><img src="assets/screenshots/04-live-vulnerability-evidence.png" alt="Live AI-supported security evidence streamed during a scan"></td>
  </tr>
  <tr>
    <td align="center"><strong>Understand the security impact</strong></td>
    <td align="center"><strong>Review the recommended fix</strong></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/05-finding-analysis.png" alt="Security finding analysis and possible impact"></td>
    <td><img src="assets/screenshots/06-recommended-fix.png" alt="Recommended security fix and safer replacement code"></td>
  </tr>
  <tr>
    <td align="center"><strong>Review the classification</strong></td>
    <td align="center"><strong>Inspect multiple AI-supported findings</strong></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/07-finding-verification.png" alt="CWE OWASP and Bandit verification details"></td>
    <td><img src="assets/screenshots/08-multiple-findings.png" alt="Multiple AI-supported findings from one repository scan"></td>
  </tr>
</table>

</details>

<details>
<summary><strong>3. Repositories, history, and system status</strong></summary>
<br>

<table>
  <tr>
    <td align="center"><strong>Monitored repositories</strong></td>
    <td align="center"><strong>Persistent scan history</strong></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/09-monitored-repositories.png" alt="Monitored repositories in SecureRepo AI"></td>
    <td><img src="assets/screenshots/10-scan-history.png" alt="SecureRepo AI local scan history"></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><strong>Kaggle backend and system status</strong></td>
  </tr>
  <tr>
    <td colspan="2"><img src="assets/screenshots/12-system-settings.png" alt="SecureRepo AI system settings and Kaggle backend status"></td>
  </tr>
</table>

</details>

---

# 📈 Results

SecureRepo AI is a working end-to-end prototype that combines Bandit evidence, RAG guidance, and a fine-tuned Qwen model to generate AI-supported findings in a schema-validated report.

A clean result only means no supported issues were found in the analyzed files and code sections; it does not prove that the repository is secure.

---

# 🔮 Future Improvements

* Add support for more programming languages and private repositories
* Build a formal benchmark for accuracy and false-positive testing
* Deploy the backend permanently instead of using a temporary Kaggle/ngrok session

---

# 📚 About the Challenge

This project was developed as part of the [**Tips Hindawi**](https://www.tipshindawi.com/) **Challenge (June–July 2026)**.

[Tips Hindawi](https://www.tipshindawi.com/) is the internships department of [**Edrak for Ai**](https://edrak4ai.com/en), and the challenge encourages participants to build real-world projects, apply practical skills, and showcase their work through GitHub.

For more information about the challenge, training programs, and upcoming batches, visit the official [Tips Hindawi](https://www.tipshindawi.com/) website.

---

# 📄 License

Licensed under the [MIT License](LICENSE).
