import re
import unicodedata
from datetime import datetime
import jiwer
import difflib
import string
import argparse

def read_transcript(filename, speaker='FA1', min_onset=0, max_offset=59999, use_utterance_count=False, max_utterances=None):
    """
    Read transcript file and extract speech for specified speaker.
    Can filter by time range OR by utterance count.
    """
    utterances = []
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 6:
                continue
            
            if parts[0] == speaker and parts[1] == speaker:
                try:
                    onset = int(parts[2])
                    offset = int(parts[3])
                    text = parts[5]
                    
                    if use_utterance_count:
                        utterances.append(text)
                        if max_utterances and len(utterances) >= max_utterances:
                            break
                    else:
                        if onset >= min_onset and offset <= max_offset:
                            utterances.append(text)
                except (ValueError, IndexError):
                    continue
    
    return utterances

def remove_special_annotations(text):
    """
    Remove all special CHAT format annotations and symbols:
    - Content within square brackets [...]
    - Content within angle brackets <...>
    - The patterns +//, +<
    - xxx (filler/unintelligible marker)
    - Entire words starting with @ or & (e.g., @ahahah, &dodod)
    - + and - symbols
    """
    # Remove content within square brackets
    text = re.sub(r'\[.*?\]', '', text)
    
    # Remove content within angle brackets
   # text = re.sub(r'<.*?>', '', text)
    
    # Remove specific patterns
    text = text.replace('+//', '')
    text = text.replace('+<', '')
    
    # Remove xxx (case insensitive)
    text = re.sub(r'\bxxx\b', '', text, flags=re.IGNORECASE)
    
    # Remove entire words starting with @ or & (including the symbol)
    # This matches @ or & followed by word characters (letters, numbers, hyphens)
    # Stops at punctuation like commas, periods, etc.
    text = re.sub(r'[@&][^\s]+', '', text)
    
    # Remove + and - symbols
    text = text.replace('+', '')
    text = text.replace('-', '')
    
    return text

def remove_diacritics_except_n(text):
    """
    Remove diacritics from vowels but preserve ñ.
    """
    text = text.replace('ñ', '|||NTILDE|||')
    text = text.replace('Ñ', '|||NTILDE_UPPER|||')
    
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    
    text = text.replace('|||NTILDE|||', 'ñ')
    text = text.replace('|||NTILDE_UPPER|||', 'Ñ')
    
    return text

def remove_punctuation_and_special_chars(text):
    """
    Remove all punctuation and special characters except spaces.
    This handles cases like "Yes," -> "yes"
    """
    # Remove all punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Remove any remaining special characters except letters, numbers, and spaces
    text = re.sub(r'[^a-zA-Z0-9\sñÑáéíóúÁÉÍÓÚüÜ]', '', text)
    
    return text

def clean_text(text, normalize_diacritics=False):
    """
    Clean and normalize text for comparison.
    Final step: convert to lowercase and remove all special characters.
    """
    # Remove all special annotations
    text = remove_special_annotations(text)
    
    # Normalize diacritics if requested (for Spanish)
    if normalize_diacritics:
        text = remove_diacritics_except_n(text)
    
    # Remove punctuation and special characters
    text = remove_punctuation_and_special_chars(text)
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Convert to lowercase (FINAL STEP)
    text = text.lower()
    
    return text

def calculate_detailed_metrics(reference, hypothesis):
    """
    Calculate detailed metrics using jiwer library.
    Returns metrics and detailed error analysis.
    """
    # Use jiwer.process_words for detailed word-level analysis
    output = jiwer.process_words(reference, hypothesis)

    # Calculate character-level metrics
    char_error_rate = jiwer.cer(reference, hypothesis)

    # Extract detailed information
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    results = {
        'wer': output.wer,
        'mer': output.mer,
        'wil': output.wil,
        'wip': output.wip,
        'cer': char_error_rate,
        'hits': output.hits,
        'substitutions': output.substitutions,
        'deletions': output.deletions,
        'insertions': output.insertions,
        'ref_words_count': len(ref_words),
        'hyp_words_count': len(hyp_words),
        'ref_chars_count': len(reference),
        'hyp_chars_count': len(hypothesis)
    }

    return results

def get_alignment_details(reference, hypothesis):
    """
    Get detailed alignment information for word-level analysis.
    This provides the actual words that were substituted, deleted, or inserted.
    """
    details = {
        'hits': [],
        'substitutions': [],
        'deletions': [],
        'insertions': []
    }

    # Use jiwer.process_words for alignment (provides alignment chunks with indices)
    if hasattr(jiwer, 'process_words'):
        output = jiwer.process_words(reference, hypothesis)
        ref_words = output.references[0]
        hyp_words = output.hypotheses[0]
        alignments = output.alignments[0]

        for chunk in alignments:
            ref_slice = ref_words[chunk.ref_start_idx:chunk.ref_end_idx]
            hyp_slice = hyp_words[chunk.hyp_start_idx:chunk.hyp_end_idx]

            if chunk.type == 'equal':
                details['hits'].extend(ref_slice)
            elif chunk.type == 'substitute':
                # Pair up words for substitutions
                for ref_word, hyp_word in zip(ref_slice, hyp_slice):
                    details['substitutions'].append((ref_word, hyp_word))
                # Handle uneven spans
                if len(ref_slice) > len(hyp_slice):
                    details['deletions'].extend(ref_slice[len(hyp_slice):])
                elif len(hyp_slice) > len(ref_slice):
                    details['insertions'].extend(hyp_slice[len(ref_slice):])
            elif chunk.type == 'delete':
                details['deletions'].extend(ref_slice)
            elif chunk.type == 'insert':
                details['insertions'].extend(hyp_slice)

        return details

    # Fallback: use difflib SequenceMatcher on tokenized (whitespace-split) inputs
    ref_tokens = reference.split()
    hyp_tokens = hypothesis.split()
    sm = difflib.SequenceMatcher(None, ref_tokens, hyp_tokens)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            details['hits'].extend(ref_tokens[i1:i2])
        elif tag == 'replace':
            # Expand into per-token substitutions, with extra tokens as deletions/insertions
            ref_span = ref_tokens[i1:i2]
            hyp_span = hyp_tokens[j1:j2]
            minlen = min(len(ref_span), len(hyp_span))
            for k in range(minlen):
                details['substitutions'].append((ref_span[k], hyp_span[k]))
            details['deletions'].extend(ref_span[minlen:])
            details['insertions'].extend(hyp_span[minlen:])
        elif tag == 'delete':
            details['deletions'].extend(ref_tokens[i1:i2])
        elif tag == 'insert':
            details['insertions'].extend(hyp_tokens[j1:j2])

    return details

def format_detailed_report(language, speaker, results, alignment_details, ref_text, hyp_text, timestamp):
    """
    Format a detailed report similar to the transcript comparison tool format.
    """
    lines = []
    
    lines.append("=" * 80)
    lines.append(f"DETAILED TRANSCRIPTION EVALUATION REPORT - {language.upper()}")
    lines.append("=" * 80)
    lines.append(f"Generated on: {timestamp}")
    lines.append(f"Speaker: {speaker}")
    lines.append(f"Language: {language}")
    lines.append("")
    lines.append("Preprocessing Applied:")
    lines.append("  - CHAT format annotations removed")
    lines.append("  - Special characters and punctuation removed")
    if language.lower() == 'spanish':
        lines.append("  - Diacritics normalized (except ñ)")
    lines.append("  - Text converted to lowercase")
    lines.append("")
    
    lines.append("-" * 80)
    lines.append("WORD-LEVEL ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"Word Error Rate (WER):           {results['wer']:.4f} ({results['wer']:.2%})")
    lines.append(f"Match Error Rate (MER):          {results['mer']:.4f} ({results['mer']:.2%})")
    lines.append(f"Word Information Lost (WIL):     {results['wil']:.4f} ({results['wil']:.2%})")
    lines.append(f"Word Information Preserved (WIP): {results['wip']:.4f} ({results['wip']:.2%})")
    lines.append("")
    
    lines.append("Word Counts:")
    lines.append(f"  Total Reference Words:  {results['ref_words_count']}")
    lines.append(f"  Total Hypothesis Words: {results['hyp_words_count']}")
    lines.append(f"  Hits (Correct):         {results['hits']}")
    lines.append(f"  Substitutions:          {results['substitutions']}")
    lines.append(f"  Deletions:              {results['deletions']}")
    lines.append(f"  Insertions:             {results['insertions']}")
    lines.append(f"  Total Errors:           {results['substitutions'] + results['deletions'] + results['insertions']}")
    lines.append(f"  Accuracy:               {(results['hits'] / results['ref_words_count'] * 100):.2f}%")
    lines.append("")
    
    lines.append("Alignment Explanation:")
    lines.append(f"  Reference alignment: {results['hits']} correct + {results['substitutions']} substituted + {results['deletions']} deleted = {results['ref_words_count']} words")
    lines.append(f"  Hypothesis alignment: {results['hits']} correct + {results['substitutions']} substituted + {results['insertions']} inserted = {results['hyp_words_count']} words")
    lines.append(f"  Note: Deletions = words in reference but missing in hypothesis")
    lines.append(f"        Insertions = extra words in hypothesis not in reference")
    lines.append(f"  WER Calculation: ({results['substitutions']} + {results['deletions']} + {results['insertions']}) / {results['ref_words_count']} = {results['wer']:.2%}")
    lines.append("")
    
    # Detailed word-level errors - SHOW ALL
    if alignment_details['hits']:
        lines.append(f"Correctly Recognized Words (Hits) - Total: {len(alignment_details['hits'])}:")
        for i, word in enumerate(alignment_details['hits'], 1):
            lines.append(f"  {i}. '{word}'")
        lines.append("")
    
    if alignment_details['substitutions']:
        lines.append(f"Word Substitutions (Reference -> Hypothesis) - Total: {len(alignment_details['substitutions'])}:")
        for i, (ref_word, hyp_word) in enumerate(alignment_details['substitutions'], 1):
            lines.append(f"  {i}. '{ref_word}' -> '{hyp_word}'")
        lines.append("")
    
    if alignment_details['deletions']:
        lines.append(f"Word Deletions (Missing from hypothesis) - Total: {len(alignment_details['deletions'])}:")
        for i, word in enumerate(alignment_details['deletions'], 1):
            lines.append(f"  {i}. '{word}'")
        lines.append("")
    
    if alignment_details['insertions']:
        lines.append(f"Word Insertions (Extra in hypothesis) - Total: {len(alignment_details['insertions'])}:")
        for i, word in enumerate(alignment_details['insertions'], 1):
            lines.append(f"  {i}. '{word}'")
        lines.append("")
    
    # Character-level analysis
    lines.append("-" * 80)
    lines.append("CHARACTER-LEVEL ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"Character Error Rate (CER): {results['cer']:.4f} ({results['cer']:.2%})")
    lines.append(f"Total Reference Characters: {results['ref_chars_count']}")
    lines.append(f"Total Hypothesis Characters: {results['hyp_chars_count']}")
    lines.append("")
    
    # Text samples
    lines.append("-" * 80)
    lines.append("COMPLETE TEXT")
    lines.append("-" * 80)
    lines.append(f"Reference (Gold Standard) - Total length: {len(ref_text)} characters:")
    lines.append(f"  {ref_text}")
    lines.append("")
    lines.append(f"Hypothesis (Trainee) - Total length: {len(hyp_text)} characters:")
    lines.append(f"  {hyp_text}")
    lines.append("")
    
    return lines

def process_speaker(gold_file, trainee_file, speaker, language, min_onset, max_offset, 
                   normalize_diacritics, output_lines, use_utterance_count=False, max_utterances=None):
    """
    Process a single speaker's transcript with detailed error analysis using jiwer.
    """
    def print_and_save(text):
        print(text)
        output_lines.append(text)
    
    print_and_save(f"\n--- Processing {language} - Speaker: {speaker} ---")
    
    # Read transcripts
    gold_utterances = read_transcript(gold_file, speaker=speaker, 
                                     min_onset=min_onset, max_offset=max_offset,
                                     use_utterance_count=use_utterance_count,
                                     max_utterances=max_utterances)
    trainee_utterances = read_transcript(trainee_file, speaker=speaker, 
                                        min_onset=min_onset, max_offset=max_offset,
                                        use_utterance_count=use_utterance_count,
                                        max_utterances=max_utterances)
    
    if use_utterance_count:
        print_and_save(f"Utterances found (by sequential order):")
    else:
        print_and_save(f"Utterances found (by time window):")
    print_and_save(f"  Gold standard: {len(gold_utterances)}")
    print_and_save(f"  Trainee: {len(trainee_utterances)}")
    
    if len(gold_utterances) == 0 and len(trainee_utterances) == 0:
        print_and_save(f"  No utterances found for {speaker} - skipping")
        return None
    
    # Combine and clean
    gold_text = ' '.join(gold_utterances)
    trainee_text = ' '.join(trainee_utterances)
    
    gold_clean = clean_text(gold_text, normalize_diacritics=normalize_diacritics)
    trainee_clean = clean_text(trainee_text, normalize_diacritics=normalize_diacritics)
    
    print_and_save(f"\nGold standard text (cleaned, first 150 chars):")
    print_and_save(f"  {gold_clean[:150]}{'...' if len(gold_clean) > 150 else ''}")
    print_and_save(f"\nTrainee text (cleaned, first 150 chars):")
    print_and_save(f"  {trainee_clean[:150]}{'...' if len(trainee_clean) > 150 else ''}")
    
    # Calculate metrics using jiwer
    results = calculate_detailed_metrics(gold_clean, trainee_clean)
    
    # Get alignment details
    alignment_details = get_alignment_details(gold_clean, trainee_clean)
    
    print_and_save(f"\nResults for {speaker} ({language}):")
    print_and_save(f"  WER: {results['wer']:.2%}")
    print_and_save(f"  MER: {results['mer']:.2%}")
    print_and_save(f"  WIL: {results['wil']:.2%}")
    print_and_save(f"  WIP: {results['wip']:.2%}")
    print_and_save(f"  CER: {results['cer']:.2%}")
    print_and_save(f"  Accuracy: {(results['hits'] / results['ref_words_count'] * 100):.2f}%")
    
    return {
        'speaker': speaker,
        'language': language,
        'results': results,
        'alignment_details': alignment_details,
        'ref_text': gold_clean,
        'hyp_text': trainee_clean
    }

def write_detailed_report(result, filename):
    """
    Write detailed report to file for a single language.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = format_detailed_report(
        result['language'],
        result['speaker'],
        result['results'],
        result['alignment_details'],
        result['ref_text'],
        result['hyp_text'],
        timestamp
    )
    
    with open(filename, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(line + '\n')
    
    print(f"\nDetailed {result['language']} report saved to: {filename}")

def generate_html_report(result, html_filename):
    """
    Generate a beautiful HTML visualization of the report.
    """
    # Create ISO timestamp for JavaScript to parse (UTC-based)
    now = datetime.now()
    timestamp_iso = now.isoformat()
    timestamp_display = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # Prepare data
    wer = result['results']['wer'] * 100
    cer = result['results']['cer'] * 100
    mer = result['results']['mer'] * 100
    wil = result['results']['wil'] * 100
    wip = result['results']['wip'] * 100
    accuracy = (result['results']['hits'] / result['results']['ref_words_count'] * 100) if result['results']['ref_words_count'] > 0 else 0
    
    # Create HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript Evaluation Report - {result['speaker']} ({result['language']})</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
        }}

        .header p {{
            font-size: 1.1em;
            opacity: 0.95;
        }}

        .content {{
            padding: 40px;
        }}

        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .info-card {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .info-card h3 {{
            color: #667eea;
            font-size: 0.9em;
            text-transform: uppercase;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }}

        .info-card p {{
            color: #2d3748;
            font-size: 1.2em;
            font-weight: bold;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}

        .metric-card {{
            background: white;
            border-left: 4px solid #667eea;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        }}

        .metric-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }}

        .metric-card.good {{
            border-left-color: #48bb78;
        }}

        .metric-card.warning {{
            border-left-color: #ed8936;
        }}

        .metric-card.error {{
            border-left-color: #f56565;
        }}

        .metric-label {{
            font-size: 0.9em;
            color: #718096;
            margin-bottom: 5px;
        }}

        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #2d3748;
        }}

        .metric-subtext {{
            font-size: 0.85em;
            color: #a0aec0;
            margin-top: 5px;
        }}

        .section {{
            margin: 40px 0;
            background: #f8f9fa;
            padding: 30px;
            border-radius: 15px;
        }}

        .section h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}

        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}

        .error-list {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin: 15px 0;
            max-height: 400px;
            overflow-y: auto;
        }}

        .error-item {{
            padding: 12px;
            margin: 8px 0;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 0.95em;
        }}

        .error-item.substitution {{
            background: #fff5f5;
            border-left: 4px solid #f56565;
        }}

        .error-item.deletion {{
            background: #fef5e7;
            border-left: 4px solid #ed8936;
        }}

        .error-item.insertion {{
            background: #e6f7ff;
            border-left: 4px solid #4299e1;
        }}

        .error-item.hit {{
            background: #f0fff4;
            border-left: 4px solid #48bb78;
        }}

        .error-badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: bold;
            margin-right: 10px;
        }}

        .badge-substitution {{
            background: #f56565;
            color: white;
        }}

        .badge-deletion {{
            background: #ed8936;
            color: white;
        }}

        .badge-insertion {{
            background: #4299e1;
            color: white;
        }}

        .badge-hit {{
            background: #48bb78;
            color: white;
        }}

        .text-comparison {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }}

        .text-box {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}

        .text-box h3 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.2em;
        }}

        .text-box pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            line-height: 1.6;
            color: #2d3748;
            max-height: 400px;
            overflow-y: auto;
        }}

        .collapsible {{
            cursor: pointer;
            padding: 15px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            width: 100%;
            text-align: left;
            font-size: 1.1em;
            margin: 10px 0;
            transition: all 0.3s ease;
        }}

        .collapsible:hover {{
            background: #764ba2;
        }}

        .collapsible:after {{
            content: '\\002B';
            color: white;
            font-weight: bold;
            float: right;
            margin-left: 5px;
        }}

        .collapsible.active:after {{
            content: "\\2212";
        }}

        .collapsible-content {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
            background: white;
            border-radius: 0 0 8px 8px;
        }}

        .collapsible-content.active {{
            max-height: 2000px;
            overflow-y: auto;
        }}

        @media (max-width: 768px) {{
            .text-comparison {{
                grid-template-columns: 1fr;
            }}

            .header h1 {{
                font-size: 1.8em;
            }}

            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Transcript Evaluation Report</h1>
            <p>{result['language']} - Speaker: {result['speaker']}</p>
        </div>

        <div class="content">
            <div class="info-grid">
                <div class="info-card">
                    <h3>Speaker</h3>
                    <p>{result['speaker']}</p>
                </div>
                <div class="info-card">
                    <h3>Language</h3>
                    <p>{result['language']}</p>
                </div>
                <div class="info-card">
                    <h3>Report Date</h3>
                    <p id="report-timestamp">{timestamp_display}</p>
                </div>
                <div class="info-card">
                    <h3>Total Words</h3>
                    <p>{result['results']['ref_words_count']}</p>
                </div>
            </div>

            <div class="metrics-grid">
                <div class="metric-card {'good' if accuracy >= 90 else 'warning' if accuracy >= 70 else 'error'}">
                    <div class="metric-label">Accuracy</div>
                    <div class="metric-value">{accuracy:.2f}%</div>
                    <div class="metric-subtext">{result['results']['hits']} correct words</div>
                </div>
                <div class="metric-card {'good' if wer < 10 else 'warning' if wer < 30 else 'error'}">
                    <div class="metric-label">Word Error Rate</div>
                    <div class="metric-value">{wer:.2f}%</div>
                    <div class="metric-subtext">Lower is better</div>
                </div>
                <div class="metric-card {'good' if cer < 10 else 'warning' if cer < 30 else 'error'}">
                    <div class="metric-label">Character Error Rate</div>
                    <div class="metric-value">{cer:.2f}%</div>
                    <div class="metric-subtext">Lower is better</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Word Info Preserved</div>
                    <div class="metric-value">{wip:.2f}%</div>
                    <div class="metric-subtext">Higher is better</div>
                </div>
            </div>

            <div class="section">
                <h2>📈 Error Distribution</h2>
                <div class="chart-container">
                    <canvas id="errorChart"></canvas>
                </div>
            </div>

            <div class="section">
                <h2>📊 Performance Metrics</h2>
                <div class="chart-container">
                    <canvas id="metricsChart"></canvas>
                </div>
            </div>

            <div class="section">
                <h2>🔍 Word-Level Analysis</h2>
                <div class="chart-container">
                    <canvas id="wordChart"></canvas>
                </div>
            </div>

            <div class="section">
                <h2>✅ Correctly Recognized Words ({len(result['alignment_details']['hits'])})</h2>
                <button class="collapsible">View All Hits</button>
                <div class="collapsible-content">
                    <div class="error-list">
                        {''.join([f'''
                        <div class="error-item hit">
                            <span class="error-badge badge-hit">{i+1}</span>
                            <strong>{word}</strong>
                        </div>
                        ''' for i, word in enumerate(result['alignment_details']['hits'][:100])])}
                        {f'<p style="text-align: center; padding: 15px; color: #718096;">... and {len(result["alignment_details"]["hits"]) - 100} more</p>' if len(result['alignment_details']['hits']) > 100 else ''}
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>🔄 Substitutions ({len(result['alignment_details']['substitutions'])})</h2>
                <button class="collapsible">View All Substitutions</button>
                <div class="collapsible-content">
                    <div class="error-list">
                        {''.join([f'''
                        <div class="error-item substitution">
                            <span class="error-badge badge-substitution">{i+1}</span>
                            '<strong>{ref_word}</strong>' → '<strong>{hyp_word}</strong>'
                        </div>
                        ''' for i, (ref_word, hyp_word) in enumerate(result['alignment_details']['substitutions'])])}
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>➖ Deletions ({len(result['alignment_details']['deletions'])})</h2>
                <button class="collapsible">View All Deletions</button>
                <div class="collapsible-content">
                    <div class="error-list">
                        {''.join([f'''
                        <div class="error-item deletion">
                            <span class="error-badge badge-deletion">{i+1}</span>
                            Missing: '<strong>{word}</strong>'
                        </div>
                        ''' for i, word in enumerate(result['alignment_details']['deletions'])])}
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>➕ Insertions ({len(result['alignment_details']['insertions'])})</h2>
                <button class="collapsible">View All Insertions</button>
                <div class="collapsible-content">
                    <div class="error-list">
                        {''.join([f'''
                        <div class="error-item insertion">
                            <span class="error-badge badge-insertion">{i+1}</span>
                            Extra: '<strong>{word}</strong>'
                        </div>
                        ''' for i, word in enumerate(result['alignment_details']['insertions'])])}
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>📝 Text Comparison</h2>
                <div class="text-comparison">
                    <div class="text-box">
                        <h3>Reference (Gold Standard)</h3>
                        <pre>{result['ref_text']}</pre>
                    </div>
                    <div class="text-box">
                        <h3>Hypothesis (Trainee)</h3>
                        <pre>{result['hyp_text']}</pre>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Convert timestamp to user's local timezone
        document.addEventListener('DOMContentLoaded', function() {{
            const timestampElement = document.getElementById('report-timestamp');
            const isoTimestamp = '{timestamp_iso}';
            const date = new Date(isoTimestamp);
            
            // Format: "Nov 14, 2025, 2:30:45 PM PST"
            const options = {{
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZoneName: 'short'
            }};
            
            timestampElement.textContent = date.toLocaleString('en-US', options);
        }});

        // Initialize collapsibles
        const collapsibles = document.querySelectorAll('.collapsible');
        collapsibles.forEach(coll => {{
            coll.addEventListener('click', function() {{
                this.classList.toggle('active');
                const content = this.nextElementSibling;
                content.classList.toggle('active');
            }});
        }});

        // Error Distribution Chart
        const errorCtx = document.getElementById('errorChart').getContext('2d');
        new Chart(errorCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Correct', 'Substitutions', 'Deletions', 'Insertions'],
                datasets: [{{
                    data: [{result['results']['hits']}, {result['results']['substitutions']}, {result['results']['deletions']}, {result['results']['insertions']}],
                    backgroundColor: ['#48bb78', '#f56565', '#ed8936', '#4299e1'],
                    borderWidth: 2,
                    borderColor: '#fff'
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{
                            padding: 20,
                            font: {{ size: 14 }}
                        }}
                    }},
                    title: {{
                        display: true,
                        text: 'Word-Level Error Distribution',
                        font: {{ size: 18 }}
                    }}
                }}
            }}
        }});

        // Performance Metrics Chart
        const metricsCtx = document.getElementById('metricsChart').getContext('2d');
        new Chart(metricsCtx, {{
            type: 'bar',
            data: {{
                labels: ['Accuracy', 'WER', 'CER', 'MER', 'WIP'],
                datasets: [{{
                    label: 'Percentage',
                    data: [{accuracy:.2f}, {wer:.2f}, {cer:.2f}, {mer:.2f}, {wip:.2f}],
                    backgroundColor: ['#48bb78', '#f56565', '#ed8936', '#4299e1', '#667eea'],
                    borderWidth: 1,
                    borderColor: '#2d3748'
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        max: 100,
                        ticks: {{
                            callback: function(value) {{
                                return value + '%';
                            }}
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{ display: false }},
                    title: {{
                        display: true,
                        text: 'Performance Metrics Overview',
                        font: {{ size: 18 }}
                    }}
                }}
            }}
        }});

        // Word Count Chart
        const wordCtx = document.getElementById('wordChart').getContext('2d');
        new Chart(wordCtx, {{
            type: 'bar',
            data: {{
                labels: ['Reference Words', 'Hypothesis Words'],
                datasets: [{{
                    label: 'Word Count',
                    data: [{result['results']['ref_words_count']}, {result['results']['hyp_words_count']}],
                    backgroundColor: ['#667eea', '#764ba2'],
                    borderWidth: 1,
                    borderColor: '#2d3748'
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }},
                plugins: {{
                    legend: {{ display: false }},
                    title: {{
                        display: true,
                        text: 'Word Count Comparison',
                        font: {{ size: 18 }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""
    
    # Write HTML file
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML report saved to: {html_filename}")

def parse_arguments():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Enhanced Transcript Comparison Tool with jiwer - Multi-Speaker Support',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single speaker
  python script.py --gold-file gold_en.txt --trainee-file trainee_en.txt \\
                   --speakers FA1 --language English --min-onset 0 --max-offset 5999

  # Multiple speakers
  python script.py --gold-file gold_es.txt --trainee-file trainee_es.txt \\
                   --speakers FA1 MAL CHI --language Spanish \\
                   --use-utterance-count --max-utterances 21 --normalize-diacritics

  # All three common speakers with time window
  python script.py --gold-file gold.txt --trainee-file trainee.txt \\
                   --speakers FA1 MAL CHI --language English \\
                   --min-onset 0 --max-offset 10000
        """
    )
    
    parser.add_argument('--gold-file', required=True,
                       help='Gold standard transcript file path')
    parser.add_argument('--trainee-file', required=True,
                       help='Trainee transcript file path')
    parser.add_argument('--speakers', nargs='+', default=['FA1'],
                       help='Speaker ID(s) to extract (space-separated, e.g., FA1 MAL CHI). Default: FA1')
    parser.add_argument('--language', required=True, choices=['English', 'Spanish'],
                       help='Language of the transcript')
    parser.add_argument('--min-onset', type=int, default=0,
                       help='Minimum onset time in milliseconds (default: 0)')
    parser.add_argument('--max-offset', type=int, default=59999,
                       help='Maximum offset time in milliseconds (default: 59999)')
    parser.add_argument('--use-utterance-count', action='store_true',
                       help='Use utterance count instead of time window')
    parser.add_argument('--max-utterances', type=int, default=None,
                       help='Maximum number of utterances to process (only with --use-utterance-count)')
    parser.add_argument('--normalize-diacritics', action='store_true',
                       help='Normalize diacritics (recommended for Spanish)')
    parser.add_argument('--output-prefix', default=None,
                       help='Output report filename prefix (default: detailed_{language}_{speaker}_evaluation.txt)')
    
    return parser.parse_args()

def main():
    """
    Main function with command line argument support for multiple speakers.
    """
    args = parse_arguments()
    
    output_lines = []
    all_results = []
    
    def print_and_save(text):
        print(text)
        output_lines.append(text)
    
    print_and_save("Enhanced Transcript Comparison Tool with jiwer - Multi-Speaker Support")
    print_and_save("=" * 80)
    print_and_save(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_and_save("")
    
    # Display configuration
    print_and_save(f"Configuration:")
    print_and_save(f"  Gold file: {args.gold_file}")
    print_and_save(f"  Trainee file: {args.trainee_file}")
    print_and_save(f"  Speakers: {', '.join(args.speakers)}")
    print_and_save(f"  Language: {args.language}")
    if args.use_utterance_count:
        print_and_save(f"  Mode: Utterance count")
        print_and_save(f"  Max utterances: {args.max_utterances if args.max_utterances else 'All'}")
    else:
        print_and_save(f"  Mode: Time window")
        print_and_save(f"  Time range: {args.min_onset} - {args.max_offset} ms")
    print_and_save(f"  Normalize diacritics: {args.normalize_diacritics}")
    print_and_save("")
    
    # Process each speaker
    for speaker in args.speakers:
        result = process_speaker(
            gold_file=args.gold_file,
            trainee_file=args.trainee_file,
            speaker=speaker,
            language=args.language,
            min_onset=args.min_onset,
            max_offset=args.max_offset,
            normalize_diacritics=args.normalize_diacritics,
            output_lines=output_lines,
            use_utterance_count=args.use_utterance_count,
            max_utterances=args.max_utterances
        )
        
        if result:
            all_results.append(result)
            
            # Generate output filename
            if args.output_prefix:
                output_filename = f'{args.output_prefix}_{speaker}.txt'
                html_filename = f'{args.output_prefix}_{speaker}.html'
            else:
                output_filename = f'detailed_{args.language.lower()}_{speaker}_evaluation.txt'
                html_filename = f'detailed_{args.language.lower()}_{speaker}_evaluation.html'
            
            # Write detailed report for this speaker
            write_detailed_report(result, output_filename)
            
            # Generate HTML report for this speaker
            generate_html_report(result, html_filename)
    
    # Generate summary report
    if all_results:
        print_and_save(f"\n{'='*80}")
        print_and_save("OVERALL EVALUATION SUMMARY")
        print_and_save(f"{'='*80}")
        print_and_save(f"Language: {args.language}")
        print_and_save(f"Speakers Processed: {len(all_results)}")
        print_and_save("")
        
        for result in all_results:
            print_and_save(f"Speaker {result['speaker']}:")
            print_and_save(f"  WER: {result['results']['wer']:.2%}")
            print_and_save(f"  CER: {result['results']['cer']:.2%}")
            print_and_save(f"  Accuracy: {(result['results']['hits'] / result['results']['ref_words_count'] * 100):.2f}%")
            print_and_save(f"  Total words: {result['results']['ref_words_count']}")
            print_and_save("")
        
        # Calculate averages
        avg_wer = sum(r['results']['wer'] for r in all_results) / len(all_results)
        avg_cer = sum(r['results']['cer'] for r in all_results) / len(all_results)
        total_words = sum(r['results']['ref_words_count'] for r in all_results)
        total_hits = sum(r['results']['hits'] for r in all_results)
        avg_accuracy = (total_hits / total_words * 100) if total_words > 0 else 0
        
        print_and_save(f"Average Metrics Across All Speakers:")
        print_and_save(f"  Average WER: {avg_wer:.2%}")
        print_and_save(f"  Average CER: {avg_cer:.2%}")
        print_and_save(f"  Overall Accuracy: {avg_accuracy:.2f}%")
        print_and_save(f"  Total Words Processed: {total_words}")
    else:
        print_and_save("\nNo results generated - no utterances found for any speaker.")
    
    # Write summary file
    summary_file = f'evaluation_summary_{args.language.lower()}_all_speakers.txt'
    with open(summary_file, 'w', encoding='utf-8') as f:
        for line in output_lines:
            f.write(line + '\n')
    print_and_save(f"\nOverall summary saved to: {summary_file}")

if __name__ == '__main__':
    main()
