# Transcript Evaluation Tool

A comprehensive tool for evaluating transcript accuracy by comparing human annotations against gold standard transcripts. Available as both a **command-line tool** and a **beautiful web application**.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

### Web Application
- **User Authentication** - Secure login system with admin user management
- **File Upload** - Upload human annotated and gold standard transcript files
- **Multi-Speaker Support** - Evaluate multiple speakers simultaneously
- **Interactive Results** - Charts, color-coded metrics, collapsible error lists
- **Downloadable Reports** - Export as TXT or HTML
- **Beautiful UI** - Purple gradient theme with responsive design

### Command-Line Tool
- **Flexible Matching** - Time-based or utterance-based filtering
- **Batch Processing** - Process multiple files via scripts
- **Detailed Reports** - Complete error lists (not truncated)

### Metrics Calculated
| Metric | Description |
|--------|-------------|
| **Accuracy** | Percentage of correctly recognized words |
| **WER** | Word Error Rate - (S + D + I) / N |
| **CER** | Character Error Rate |
| **WIP** | Word Information Preserved |
| **Hits** | Correctly matched words |
| **Substitutions** | Words replaced with different words |
| **Deletions** | Words missing from hypothesis |
| **Insertions** | Extra words in hypothesis |

## Quick Start

### Option 1: Web Application

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create admin user**
   ```bash
   python -c "from app import create_admin; create_admin('admin', 'your-password')"
   ```

3. **Run the server**
   ```bash
   python app.py
   ```

4. **Open browser** at `http://localhost:5000`

### Option 2: Command Line

```bash
# English evaluation
python human_vs_gold.py --gold-file sample_files/5271-0GS0.txt \
    --trainee-file sample_files/5271-Round-1-SS.txt \
    --speakers FA1 --language English --min-onset 0 --max-offset 59999

# Spanish with diacritic normalization
python human_vs_gold.py --gold-file gold.txt --trainee-file trainee.txt \
    --speakers FA1 CHI --language Spanish --normalize-diacritics

# Utterance-based matching
python human_vs_gold.py --gold-file gold.txt --trainee-file trainee.txt \
    --speakers FA1 --language English --use-utterance-count --max-utterances 20
```

## Installation

### Prerequisites
- Python 3.10 or higher
- pip (Python package manager)

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/transcript-evaluator.git
cd transcript-evaluator

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create admin user for web app
python -c "from app import create_admin; create_admin('admin', 'your-password')"

# Run web application
python app.py
```

## Project Structure

```
transcript-evaluator/
├── app.py                 # Flask web application
├── human_vs_gold.py       # Core evaluation logic & CLI
├── config.py              # Configuration settings
├── models.py              # User authentication model
├── requirements.txt       # Python dependencies
├── database.db            # SQLite database (auto-created)
├── templates/
│   ├── base.html          # Base template
│   ├── login.html         # Login page
│   ├── register.html      # User management
│   ├── upload.html        # Evaluation form
│   └── results.html       # Results display
├── static/
│   ├── css/style.css      # Styling
│   └── uploads/           # Temporary uploads
└── sample_files/          # Example transcripts
```

## File Format

Tab-separated transcript files:
```
Speaker1  Speaker2  Onset   Offset  [Column5]  Text
FA1       FA1       0       1500    tier       hello how are you
FA1       FA1       1600    3000    tier       I am fine thank you
```

## Web Application Usage

1. **Login** with your credentials
2. **Upload Files** - Select human and gold standard transcripts
3. **Configure Settings**
   - Language: English or Spanish
   - Speakers: Select from common codes or add custom
   - Mode: Time-based or utterance-based
   - Diacritics: Enable for Spanish
4. **View Results** - Interactive charts and detailed analysis
5. **Download Reports** - TXT or HTML format

## Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `--gold-file` | Gold standard transcript file (required) |
| `--trainee-file` | Trainee transcript file (required) |
| `--speakers` | Speaker IDs (e.g., FA1 CHI MA1) |
| `--language` | English or Spanish (required) |
| `--min-onset` | Minimum onset time in ms (default: 0) |
| `--max-offset` | Maximum offset time in ms (default: 59999) |
| `--use-utterance-count` | Use utterance count instead of time |
| `--max-utterances` | Max utterances to process |
| `--normalize-diacritics` | Normalize diacritics (for Spanish) |
| `--output-prefix` | Output filename prefix |

## Common Speaker Codes

- **FA1, FA2**: Female Adult 1, 2
- **MA1, MA2**: Male Adult 1, 2
- **CHI**: Target Child
- **MC1, MC2**: Male Child 1, 2
- **FC1, FC2**: Female Child 1, 2
- **UC1, UC2**: Unidentified Child 1, 2
- **INV**: Investigator
- **EXP**: Experimenter

## Production Deployment

```bash
# Install Gunicorn
pip install gunicorn

# Run with 4 workers
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

For HTTPS, configure Nginx as a reverse proxy.

## Configuration

Edit `config.py`:
- `SECRET_KEY` - Change for production
- `UPLOAD_FOLDER` - File upload directory
- `MAX_CONTENT_LENGTH` - Max upload size (default 16MB)

## Dependencies

- Flask 3.0.0
- Flask-Login 0.6.3
- Flask-WTF 1.2.1
- Werkzeug 3.0.1
- jiwer 3.0.3
- Gunicorn 21.2.0

## License

MIT License

## Contributing

Contributions welcome! Please submit a Pull Request.

## Acknowledgments

- [jiwer](https://github.com/jitsi/jiwer) - Word Error Rate calculation
- [Chart.js](https://www.chartjs.org/) - Interactive charts
- [Flask](https://flask.palletsprojects.com/) - Web framework
