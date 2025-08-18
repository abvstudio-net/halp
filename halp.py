#!/usr/bin/env python3
"""
halp - A command line tool that provides remote-Ollama assistance.
"""

import argparse
import os
import sys
import yaml
import requests
import json
from pathlib import Path

# Default configuration
DEFAULT_CONFIG = {
    "host": "localhost:11434",
    "api_key": "",
    "model": "llama2",  # Changed default model to a more common one
    "context": {
        "include_git": True,
        "max_files": 5
    }
}

def load_config():
    """Load configuration from ~/.halp.yaml if it exists."""
    config_path = Path.home() / ".halp.yaml"
    config = DEFAULT_CONFIG.copy()
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    config.update(user_config)
        except Exception as e:
            print(f"Error loading config file: {e}", file=sys.stderr)
    
    return config

def get_context(include_git=True, max_files=5):
    """
    Gather context from the current working environment.
    This includes current directory, git info (if enabled), and recent files.
    """
    context = {
        "current_dir": os.getcwd(),
        "files": []
    }
    
    # Add git information if requested and available
    if include_git:
        try:
            import subprocess
            git_branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
                stderr=subprocess.DEVNULL
            ).decode().strip()
            context["git_branch"] = git_branch
            
            # Get modified files
            git_status = subprocess.check_output(
                ["git", "status", "--porcelain"], 
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if git_status:
                context["git_modified_files"] = git_status.split('\n')
        except:
            # Git not available or not in a git repo
            pass
    
    # Add content of current file if specified
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        try:
            with open(sys.argv[1], 'r') as f:
                context["current_file"] = {
                    "name": sys.argv[1],
                    "content": f.read()
                }
        except:
            pass
    
    return context

def list_models(config):
    """List available models from the Ollama API."""
    # Handle both http:// and https:// URLs properly
    host = config['host']
    if host.startswith('http://') or host.startswith('https://'):
        # For full URLs, use the URL as is
        base_url = host
    else:
        # For host:port format, add http://
        base_url = f"http://{host}"
    
    # Remove trailing slash if present
    base_url = base_url.rstrip('/')
    
    # Construct the API endpoint URL for models
    url = f"{base_url}/v1/models"
    
    print(f"Connecting to API endpoint: {url}")
    
    headers = {}
    # Add API key to headers if provided
    if config.get('api_key'):
        headers["Authorization"] = f"Bearer {config['api_key']}"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            response.raise_for_status()
            
        models_data = response.json()
        if "data" in models_data and isinstance(models_data["data"], list):
            return models_data["data"]
        else:
            print("Unexpected response format for models.", file=sys.stderr)
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}", file=sys.stderr)
        return []

def query_ollama(prompt, config):
    """Send a query to the Ollama API."""
    # Handle both http:// and https:// URLs properly
    host = config['host']
    if host.startswith('http://') or host.startswith('https://'):
        # For full URLs, use the URL as is
        base_url = host
    else:
        # For host:port format, add http://
        base_url = f"http://{host}"
    
    # Remove trailing slash if present
    base_url = base_url.rstrip('/')
    
    # Construct the API endpoint URL
    url = f"{base_url}/v1/chat/completions"
    
    print(f"Connecting to API endpoint: {url}")
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Add API key to headers if provided
    if config.get('api_key'):
        headers["Authorization"] = f"Bearer {config['api_key']}"
    
    data = {
        "model": config["model"],
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    
    try:
        print(f"Sending request with model: {config['model']}")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Get remote-Ollama assistance from the command line.")
    parser.add_argument("prompt", nargs="?", help="The prompt to send to Ollama")
    parser.add_argument("--model", "-m", help="Specify the model to use")
    parser.add_argument("--host", help="Specify the Ollama host (e.g., remote-ollama.example.com:11434)")
    parser.add_argument("--no-context", action="store_true", help="Don't include context in the prompt")
    parser.add_argument("--list-models", action="store_true", help="List available models from the Ollama API")
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Override config with command line arguments
    if args.host:
        config["host"] = args.host
    
    # If --list-models is provided, list available models and exit
    if args.list_models:
        print("Listing available models...")
        models = list_models(config)
        if models:
            print("\nAvailable models:")
            for model in models:
                if isinstance(model, dict) and "id" in model:
                    print(f"- {model['id']}")
                else:
                    print(f"- {model}")
        else:
            print("No models found or unable to retrieve models.")
        sys.exit(0)
    
    # If no prompt is provided, print help and exit
    if not args.prompt:
        parser.print_help()
        sys.exit(0)
    
    # Override config with model argument if provided
    if args.model:
        config["model"] = args.model
    
    # Gather context if enabled
    context_str = ""
    if not args.no_context:
        context = get_context(
            include_git=config["context"].get("include_git", True),
            max_files=config["context"].get("max_files", 5)
        )
        context_str = f"\n\nContext:\n{json.dumps(context, indent=2)}"
    
    # Construct the full prompt with context
    full_prompt = f"{args.prompt}{context_str}"
    
    # Query Ollama
    response = query_ollama(full_prompt, config)
    
    # Print the response
    if response and "choices" in response and len(response["choices"]) > 0:
        if "message" in response["choices"][0] and "content" in response["choices"][0]["message"]:
            print(response["choices"][0]["message"]["content"])
        else:
            print("Unexpected response format.", file=sys.stderr)
            print(f"Response: {response}", file=sys.stderr)
    else:
        print("No response received from Ollama.", file=sys.stderr)
        if response:
            print(f"Response: {response}", file=sys.stderr)

if __name__ == "__main__":
    main()
