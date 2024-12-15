# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "pandas",
#   "numpy",
#   "matplotlib",
#   "seaborn",
#   "chardet",
#   "scikit-learn",
#   "rich",
#   "tenacity",
#   "openai",
#   "tabulate"
# ]
# ///

import os
import sys
import re
import json
import base64
import subprocess
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from rich.console import Console
from dateutil import parser
import chardet
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
from tabulate import tabulate
import logging

# Initialize console for rich logging
console = Console()

# Configure logging for tenacity
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variable for AI Proxy token
AIPROXY_TOKEN = os.environ.get("AIPROXY_TOKEN")
if not AIPROXY_TOKEN:
    raise EnvironmentError("AIPROXY_TOKEN is not set. Please set it before running the script.")

# Retry settings
def retry_settings_with_logging():
    return retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )

@retry_settings_with_logging()
def detect_encoding(file_path):
    """Detect the encoding of a CSV file."""
    with open(file_path, 'rb') as file:
        result = chardet.detect(file.read())
        return result['encoding']

@retry_settings_with_logging()
def read_csv(file_path):
    """Read a CSV file with automatic encoding detection and flexible date parsing using regex."""
    try:
        console.log("Detecting file encoding...")
        encoding = detect_encoding(file_path)
        console.log(f"Detected encoding: {encoding}")

        df = pd.read_csv(file_path, encoding=encoding, encoding_errors='replace')

        # Attempt to parse date columns using regex
        for column in df.columns:
            if df[column].dtype == object and is_date_column(df[column]):
                console.log(f"Parsing dates in column: {column}")
                df[column] = df[column].apply(parse_date_with_regex)

        return df

    except Exception as e:
        console.log(f"[red]Error reading the file: {e}[/]")
        sys.exit(1)

def parse_date_with_regex(date_str):
    """Parse a date string using regex patterns to identify different date formats."""
    if not isinstance(date_str, str):  # Skip non-string values (e.g., NaN, float)
        return date_str  # Return the value as-is

    if not re.search(r'\d', date_str):
        return np.nan  # If no digits are found, it's not likely a date

    patterns = [
        (r"\d{2}-[A-Za-z]{3}-\d{4}", "%d-%b-%Y"),
        (r"\d{2}-[A-Za-z]{3}-\d{2}", "%d-%b-%y"),
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y"),
        (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),
    ]

    for pattern, date_format in patterns:
        if re.match(pattern, date_str):
            try:
                return pd.to_datetime(date_str, format=date_format, errors='coerce')
            except Exception as e:
                console.log(f"Error parsing date: {date_str} with format {date_format}. Error: {e}")
                return np.nan

    try:
        return parser.parse(date_str, fuzzy=True, dayfirst=False)
    except Exception as e:
        console.log(f"Error parsing date with dateutil: {date_str}. Error: {e}")
        return np.nan

def is_date_column(column):
    """Determines whether a column likely contains dates based on column name or content."""
    if isinstance(column, str):
        if any(keyword in column.lower() for keyword in ['date', 'time', 'timestamp']):
            return True

    sample_values = column.dropna().head(10)
    date_patterns = [r"\d{2}-[A-Za-z]{3}-\d{2}", r"\d{2}-[A-Za-z]{3}-\d{4}", r"\d{4}-\d{2}-\d{2}", r"\d{2}/\d{2}/\d{4}"]

    for value in sample_values:
        if isinstance(value, str):
            for pattern in date_patterns:
                if re.match(pattern, value):
                    return True
    return False

def clean_data(data):
    """Handle missing or invalid data."""
    console.log("[cyan]Cleaning data...")
    data = data.drop_duplicates()
    data = data.dropna(how='all')
    data.fillna(data.median(numeric_only=True), inplace=True)
    return data

def detect_outliers(data):
    """Detect outliers using Isolation Forest."""
    numeric_data = data.select_dtypes(include='number')
    if numeric_data.empty:
        console.log("[yellow]No numeric data found for outlier detection.")
        return data

    console.log("[cyan]Performing outlier detection...")
    model = IsolationForest(contamination=0.05, random_state=42)
    outliers = model.fit_predict(numeric_data)
    data['Outlier'] = (outliers == -1)
    return data

def perform_clustering(data):
    """Perform KMeans clustering on numeric data."""
    numeric_data = data.select_dtypes(include='number')
    if numeric_data.shape[1] < 2:
        console.log("[yellow]Insufficient numeric features for clustering.")
        return data

    console.log("[cyan]Performing clustering...")
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(numeric_data)
    kmeans = KMeans(n_clusters=3, random_state=42, n_init='auto')
    data['Cluster'] = kmeans.fit_predict(scaled_data)
    return data

def perform_pca(data):
    """Perform Principal Component Analysis (PCA) on numeric data."""
    numeric_data = data.select_dtypes(include='number')
    if numeric_data.shape[1] < 2:
        console.log("[yellow]Insufficient numeric features for PCA.")
        return data

    console.log("[cyan]Performing PCA...")
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(numeric_data)
    pca = PCA(n_components=2)
    components = pca.fit_transform(scaled_data)
    data['PCA1'] = components[:, 0]
    data['PCA2'] = components[:, 1]

    plt.figure(figsize=(8, 6))
    sns.scatterplot(x='PCA1', y='PCA2', hue='Cluster', data=data, palette='tab10')
    plt.title("PCA Scatterplot")
    return "pca_scatterplot.png"

def visualize_data(data, output_dir):
    """Generate advanced visualizations."""
    numeric_data = data.select_dtypes(include='number')

    visualizations = []

    if not numeric_data.empty:
        console.log("[cyan]Generating correlation heatmap...")
        plt.figure(figsize=(10, 8))
        sns.heatmap(numeric_data.corr(), annot=True, cmap="coolwarm")
        plt.title("Correlation Heatmap")
        heatmap_path = os.path.join(output_dir, "correlation_heatmap.png")
        plt.savefig(heatmap_path)
        plt.close()
        visualizations.append(heatmap_path)

        console.log("[cyan]Generating boxplot...")
        plt.figure(figsize=(12, 6))
        sns.boxplot(data=numeric_data)
        plt.title("Boxplot of Numeric Data")
        boxplot_path = os.path.join(output_dir, "boxplot.png")
        plt.savefig(boxplot_path)
        plt.close()
        visualizations.append(boxplot_path)

        console.log("[cyan]Generating histograms...")
        histograms_path = os.path.join(output_dir, "histograms.png")
        numeric_data.hist(figsize=(12, 10), bins=20, color='teal')
        plt.savefig(histograms_path)
        plt.close()
        visualizations.append(histograms_path)

    else:
        console.log("[yellow]No numeric data available for visualizations.")

    return visualizations

def query_llm(prompt, functions=None):
    """Queries the LLM for insights and returns the response, with function call support."""
    try:
        url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {AIPROXY_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a helpful data analysis assistant."},
                {"role": "user", "content": prompt},
            ],
        }
        if functions:
            payload["functions"] = functions
        payload_json = json.dumps(payload)
        result = subprocess.run(
            ["curl", "-X", "POST", url, "-H", f"Authorization: Bearer {AIPROXY_TOKEN}", "-H", "Content-Type: application/json", "-d", payload_json],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            response_data = json.loads(result.stdout)
            if not response_data["choices"][0]["message"].get("function_call"):
                return response_data["choices"][0]["message"]["content"]
            else:
                return response_data["choices"][0]["message"]["function_call"]
        else:
            raise Exception(f"Error in curl request: {result.stderr}")
    except Exception as e:
        console.log(f"[red]Error querying AI Proxy: {e}[/]")
        return "Error: Unable to generate narrative."


def create_story(analysis, visualizations_summary, data, has_time_series):
    """Creates a narrative using LLM based on analysis and visualizations."""
    functions = [
        {
            "name": "perform_time_series_analysis",
            "description": "Perform time series analysis if a date column is present and a time-based analysis is feasible.",
             "parameters": {
                  "type": "object",
                    "properties": {
                        "date_column": {
                            "type": "string",
                            "description": "Name of the date column in the dataset."
                         }
                        },
                       "required": ["date_column"],
              },
        },
        {
          "name": "generate_cluster_summary",
          "description": "Summarize the characteristics of identified clusters based on cluster labels",
          "parameters": {
             "type": "object",
             "properties": {
                "cluster_count": {
                     "type": "integer",
                     "description": "The number of clusters found during the analysis"
                     },
              },
             "required": ["cluster_count"],
              }
        },
        {
          "name": "generate_outlier_summary",
            "description": "Summarize the detected outliers. Highlight any unusual or interesting characteristics.",
             "parameters": {
                  "type": "object",
                    "properties": {
                         "outlier_count": {
                           "type": "integer",
                           "description": "The number of outliers detected"
                         }
                       },
                       "required": ["outlier_count"],
              }
         }
      ]
    context_str = json.dumps({
        "columns": [{"name": col, "type": str(data[col].dtype), "missing_values": data.isnull().sum()[col]} for col in data.columns],
        "example_rows": data.head(3).to_dict(orient="records"),
        "shape": data.shape,
        "summary_statistics": analysis["summary_statistics"]
    }, indent=2)

    prompt = (
        f"You are an expert data scientist.\n"
        f"Analyze the following dataset context:\n"
        f"{context_str}\n"
        f"Here is what I know about the dataset:\n"
        f"- Time series analysis is {'applicable' if has_time_series else 'not applicable'}\n"
        f"- Visualizations generated: Correlation heatmap, boxplot, histograms, PCA scatterplot.\n"
        f"Provide:\n"
        f"- A summary of the most significant findings and patterns.\n"
        f"- Recommendations for further analysis.\n"
         f"You may use any of the following functions to help you perform a more detailed analysis if required."
    )

    response = query_llm(prompt, functions=functions)
    
    analysis_summary = ""
    if not isinstance(response, dict):
         analysis_summary = response
    else:
          function_name = response["name"]
          function_args = json.loads(response["arguments"])
          if function_name == "perform_time_series_analysis":
            analysis_summary += "Performing a time series analysis..."
            analysis_summary += f"You asked me to analize the '{function_args['date_column']}' column but the requested functionality was not implemented in this version."
          elif function_name == "generate_cluster_summary":
             analysis_summary += f"Here is a summary of the generated clusters, based on the analysis we identified {function_args['cluster_count']} clusters."
             prompt_cluster = f"""
             Provide a summary of the clusters identified in the data:
             {context_str}
             The number of clusters is {function_args['cluster_count']}.
             """
             analysis_summary += query_llm(prompt_cluster)
          elif function_name == "generate_outlier_summary":
            analysis_summary += f"Here is a summary of the detected outliers, I found {function_args['outlier_count']} outliers."
            prompt_outliers = f"""
             Provide a summary of the outliers identified in the data:
             {context_str}
             The number of outliers is {function_args['outlier_count']}.
             """
            analysis_summary += query_llm(prompt_outliers)
          else:
            analysis_summary += "I couldn't understand your request, I'll proceed generating a summary without additional analysis."
    return analysis_summary

def save_results(output_dir, analysis, visualizations, story):
    """Save results to README.md and the output folder."""
    readme_path = os.path.join(output_dir, "README.md")
    with open(readme_path, "w") as f:
        f.write("# Automated Data Analysis Report\n\n")
        f.write("## Data Overview\n")
        f.write(f"**Shape**: {analysis['shape']}\n\n")
        f.write("## Summary Statistics\n")
        f.write(tabulate(pd.DataFrame(analysis["summary_statistics"]).reset_index(), headers='keys', tablefmt='github'))
        f.write("\n\n## Narrative\n")
        f.write(story)
        f.write("\n\n## Visualizations\n")
        for viz in visualizations:
            f.write(f"- ![Visualization]({os.path.basename(viz)})\n")

def create_output_folder(file_path):
    """Create a structured output folder named after the input file."""
    output_dir = os.path.splitext(os.path.basename(file_path))[0]
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir

def main():
    console.log("[cyan]Starting script...")
    if len(sys.argv) != 2:
        console.log("[red]Usage: python autolysis.py dataset.csv")
        sys.exit(1)

    file_path = sys.argv[1]
    console.log(f"[yellow]Reading file: {file_path}[/]")
    df = read_csv(file_path)
    console.log("[green]Dataframe loaded.[/]")

    # Create output folder
    output_dir = create_output_folder(file_path)

    df = clean_data(df)
    df = detect_outliers(df)
    df = perform_clustering(df)
    pca_path = perform_pca(df)
    visualizations = visualize_data(df, output_dir)
    visualizations.append(os.path.join(output_dir, pca_path))

    has_time_series = is_date_column(df)

    analysis = {
        "shape": df.shape,
        "columns": df.dtypes.to_dict(),
        "missing_values": df.isnull().sum().to_dict(),
        "summary_statistics": df.describe(include="all").to_dict(),
    }

    story = create_story(analysis, visualizations, df, has_time_series)
    save_results(output_dir, analysis, visualizations, story)

    console.log("[green]Analysis completed successfully.")

if __name__ == "__main__":
    main()
