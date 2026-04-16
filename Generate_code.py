# Project Setup Prompt for VS Code Copilot
# Project Name: Data_Analyzer_agent

# Goal: Develop an LLM-powered Agent for automated SIT signal analysis within Bosch.
# The Agent will handle data download, conversion, quality checks, visualization (using PlotStr), and report generation, with a human-in-the-loop for review.
# This project is designed for long-term maintenance, adherence to coding rules, and deployment using a Harness Engineer mindset.

# 1. Project Structure:
#    Create the following directory and file structure.
#    - .vscode/settings.json
#    - docs/ (README.md, ARCHITECTURE.md, USAGE.md, CODING_RULES.md, ENVIRONMENT_SETUP.md)
#    - config/ (agent_config.yaml, logging_config.yaml, tools_config.yaml)
#    - src/ (main.py, core/, tools/, utils/)
#    - src/core/ (agent_orchestrator.py, llm_interface.py, human_interaction.py)
#    - src/tools/ (plotstr_wrapper.py, robocopy_wrapper.py, bytesoup_converter_wrapper.py, aos_checker_wrapper.py, report_generator.py)
#    - src/utils/ (file_operations.py, config_loader.py, logger_setup.py)
#    - src/data/ (empty subdirectories: raw_bytesoup, converted_mat, plotstr_outputs, reports)
#    - tests/ (unit/test_plotstr_wrapper.py, integration/test_full_workflow.py)
#    - plotstr_original_code/ (empty directory, for MATLAB code)
#    - requirements.txt
#    - .env
#    - .gitignore
#    - Dockerfile

# 2. Initial File Content:

#    a. .gitignore: Standard Python .gitignore with added lines for .mat, .exe, .log, .vscode, .env, plotstr_original_code/ (to not track large MATLAB files).

#    b. requirements.txt:
#       Add initial dependencies:
#       - openai
#       - python-dotenv
#       - pyyaml
#       - python-pptx (for preliminary report)
#       - reportlab (for final PDF report)
#       - langchain (potential framework for LLM Agent)
#       - pydantic (for data validation, especially for tool parameters)
#       - click (for CLI interface)
#       - loguru (for enhanced logging)
#       - watchdog (for file monitoring, if needed)
#       - # matlab-engine (conditional, if PlotStr uses it)

#    c. .env:
#       Add placeholders for environment variables:
#       - BOSCH_ASKBOSCH_API_KEY=your_askbosch_api_key_here
#       - MATLAB_RUNTIME_PATH=C:/Program Files/MATLAB/R2023a/runtime
#       - PLOTSTR_EXECUTABLE_PATH=C:/Path/To/Compiled/PlotStr.exe
#       - # ... other tool paths ...

#    d. config/agent_config.yaml:
#       Initial YAML content:
#       llm_settings:
#         model_name: "gpt-4-turbo" # Placeholder, actual AskBosch model name
#         temperature: 0.7
#         max_tokens: 2000
#       agent_persona: "You are a professional SIT signal analysis expert for Bosch, automating data processing, quality checks, visualization, and report generation."
#       working_dirs:
#         base: "./src/data"
#         raw_bytesoup: "raw_bytesoup"
#         converted_mat: "converted_mat"
#         plotstr_outputs: "plotstr_outputs"
#         reports: "reports"
#       human_review_timeout_seconds: 3600

#    e. config/logging_config.yaml:
#       Basic YAML content for logging configuration using loguru (e.g., console output, file output).

#    f. config/tools_config.yaml:
#       Initial YAML content:
#       plotstr:
#         type: "executable" # or "matlab_engine"
#         path: "${PLOTSTR_EXECUTABLE_PATH}"
#         output_format: "png"
#         default_dpi: 300
#       robocopy:
#         path: "robocopy.exe" # Windows built-in
#         default_flags: "/COPYALL /DCOPY:T /E /R:1 /W:1"
#       # ... placeholders for other tools ...

#    g. src/utils/config_loader.py:
#       Write a Python class `ConfigLoader` to load YAML configurations from the `config/` directory and resolve environment variables (e.g., using `dotenv`).
#       It should have a method to load a specific config file and expose its content as attributes or a dictionary.

#    h. src/utils/logger_setup.py:
#       Write a Python function `setup_logging()` that initializes loguru based on `logging_config.yaml`.

#    i. src/main.py:
#       Basic entry point:
#       - Load configurations.
#       - Setup logging.
#       - Placeholder for starting the Agent Orchestrator.
#       - Use `click` for a simple CLI: `python main.py analyze --file <path>`.

#    j. docs/CODING_RULES.md:
#       Add a section for Bosch-specific coding rules (e.g., PEP8 adherence, docstrings for all public functions, type hints, error handling practices, security considerations).

#    k. docs/ENVIRONMENT_SETUP.md:
#       Add sections for:
#       - Python Installation (recommend Anaconda/Miniconda)
#       - VS Code setup (extensions like Python, Pylance, Copilot, Docker)
#       - MATLAB Runtime/Installation (if needed)
#       - Git setup
#       - `pip install -r requirements.txt`
#       - .env file configuration

# 3. Focus on src/tools/plotstr_wrapper.py:
#    This is the first tool we will encapsulate.
#    a. Create a Python file `src/tools/plotstr_wrapper.py`.
#    b. Inside, define a Pydantic model for PlotStr configuration (e.g., `PlotStrConfig` with executable path, output format, dpi).
#    c. Implement a class `PlotStrWrapper` that takes `PlotStrConfig` during initialization.
#    d. Inside `PlotStrWrapper`, define the following methods (as Agent tools):

#       Method 1: `plot_mat_signals(self, mat_file_path: str, signals_to_plot: list[str], output_image_name: str, title: str = "Signal Plot", plot_config: dict = None) -> str`
#          - Docstring: "Plots specified signals from a MAT file using the PlotStr tool. Generates a static image.
#            This tool requires the MAT file path, a list of signal names to plot, and a desired output image file name.
#            It returns the full path to the generated image file.
#            `plot_config` can override default plot settings like line colors, scales, etc."
#          - Implementation:
#            - Construct the command-line arguments for the compiled PlotStr executable.
#            - Use `subprocess.run()` to execute PlotStr.
#            - Handle potential errors (non-zero exit code).
#            - Return the full path to the generated image.
#            - Include a placeholder for `matlab.engine` integration as an alternative if compilation is not possible, but mark it as less preferred for deployment.

#       Method 2: `launch_plotstr_ui_for_review(self, mat_file_path: str, video_file_path: str = None) -> str`
#          - Docstring: "Launches the PlotStr Graphical User Interface (GUI) with a specified MAT file loaded, and optionally a video file for synchronized viewing.
#            This tool is for human review and analysis, and will open a separate window.
#            It returns a message indicating that the UI has been launched and the Agent is awaiting user's manual review and feedback through a separate channel.
#            The Agent cannot automatically extract analysis results from this UI."
#          - Implementation:
#            - Construct the command-line arguments to launch PlotStr GUI with specified files.
#            - Use `subprocess.Popen()` (to run non-blocking).
#            - Return a informative message.

# 4. Dockerfile:
#    Create a basic Dockerfile for a Python application.
#    - Use a suitable base image (e.g., `python:3.9-slim-buster` or a Bosch-approved base image).
#    - Copy `requirements.txt` and install dependencies.
#    - Copy the `src/` directory.
#    - Define an entrypoint for `main.py`.
#    - Add placeholders for MATLAB runtime installation if needed (complex, will be external to Docker usually).

# 5. Review and Refine:
#    - Ensure all generated files are consistent with the structure.
#    - Add comments where necessary.
#    - Ensure placeholders for Bosch-specific elements (like AskBosch API Key, Bosch-approved base images) are present.

# Let's start generating!