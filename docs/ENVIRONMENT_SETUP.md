# Environment Setup

## Prerequisites

### Python Installation

1. Install Python 3.9+ (recommended: Anaconda/Miniconda).
   ```bash
   # Using Miniconda
   conda create -n data_analyzer python=3.9
   conda activate data_analyzer
   ```

### VS Code Setup

Install the following extensions:

- **Python** (ms-python.python)
- **Pylance** (ms-python.vscode-pylance)
- **GitHub Copilot** (GitHub.copilot)
- **Docker** (ms-azuretools.vscode-docker)
- **YAML** (redhat.vscode-yaml)

### Git Setup

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@bosch.com"
```

### MATLAB Runtime (if needed)

If using PlotStr with MATLAB engine mode:

1. Download MATLAB Runtime R2023a from the Bosch internal software catalog.
2. Install to `C:\Program Files\MATLAB\R2023a\runtime`.
3. Add the runtime path to your system PATH.

## Project Setup

### 1. Clone the Repository

```bash
git clone <repository_url>
cd Data_analyzer_agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your specific paths and API keys:

- `BOSCH_ASKBOSCH_API_KEY`: Your AskBosch API key
- `MATLAB_RUNTIME_PATH`: Path to MATLAB Runtime
- `PLOTSTR_EXECUTABLE_PATH`: Path to compiled PlotStr executable

### 4. Verify Installation

```bash
python src/main.py --help
```

## Docker Setup (Optional)

```bash
docker build -t data-analyzer-agent .
docker run --env-file .env data-analyzer-agent analyze --file /data/test.mat
```
