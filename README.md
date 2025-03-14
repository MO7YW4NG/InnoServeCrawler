# InnoServeCrawler

## Overview
InnoServeCrawler is a Python-based web scraping and data processing tool specifically designed to extract competition data from the InnoServe Awards website. It automates the process of downloading related media files (such as audio from YouTube), transcribing the audio content, and leveraging Large Language Models via the Groq and Google Gemini APIs to generate detailed summaries and extract key technologies. The refined data is then stored in a structured CSV file for efficient analysis and reporting.

## Project Structure
- **main.py**: The main entry point of the project.
- **.env**: Configuration file for environment variables.
- **competition_results.csv**: CSV file that holds processed competition results.
- **downloads/**: Directory containing various media files (e.g., MP3 and TXT files) related to competitions, events, or informational content.

## Setup & Installation
1. **Python Environment**  
   Ensure you have Python installed. It is recommended to use a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```
2. **Dependencies**  
   Install required packages by running:
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Create a `requirements.txt` if external packages are used.)*

3. **Configuration**  
   Rename or update the `.env` file with the necessary configuration (such as API keys, database connection strings, etc.).

## Environment Configuration
Configure your environment by editing the `.env` file. The following API keys are required:
- **GROQ_API_KEY**: API key for accessing the Groq client (used for audio transcription).
- **GEMINI_API_KEY**: API key for accessing the Google Gemini client (used for labeling data with summaries and key technologies).

## Usage
1. **Running the Crawler**  
   Execute the main script:
   ```bash
   python main.py
   ```
   The script will perform the crawling operation, update competition results, and manage media downloads.

2. **Output Information**  
   - Processed results are stored in `competition_results.csv`.
   - Downloaded media files are saved in the `downloads/` folder.

## Contributing
Feel free to open issues or submit pull requests for improvements or bug fixes. Contributions are welcome!

## License
This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

## Acknowledgements
Credit any contributors or resources as needed.
