# TESTING halp

This guide provides 15 example commands to exercise halp’s default agent mode, quick mode, confirmation gating, and the "yolo" auto-execution directive.

Important:
- By default, any CLI command the agent wants to run will request your confirmation.
- "yolo" as the first word of your prompt enables auto-execution (equivalent to --unsafe_exec for the session) and is stripped from the task.
- `--unsafe_exec` enables auto-execution for all commands without confirmation.
- `--quick` produces a single one-pass reply without using tools.

Before testing:
- Ensure `BASE_URL`, `API_KEY`, and `DEFAULT_MODEL` are configured (`~/.halp.env` or CLI overrides).
- Review `halp --help` for all options.

## 15 Example Tests

1) Default agent: directory overview (should ask to approve a safe command like `ls`)
   
   ```bash
   halp "List the current directory with details and summarize notable items"
   ```

2) Decline confirmation path (answer "n" when prompted)
   
   ```bash
   halp "Check disk usage of the current directory and suggest cleanup options"
   ```

3) Unsafe exec flag (auto-exec, no confirmations)
   
   ```bash
   halp --unsafe_exec "Show the top 10 largest files under the current directory recursively"
   ```

4) Quick mode (no tools, single-pass)
   
   ```bash
   halp --quick "Explain what this repository does, based on filenames only"
   ```

5) YOLO auto-exec (no confirmations)
   
   ```bash
   halp "yolo show disk usage summary of the current directory"
   ```

6) YOLO via piped input (auto-exec)
   
   ```bash
   echo "yolo print working directory and current user" | halp
   ```

7) Summarize recent shell history (tests system prompt history injection)
   
   ```bash
   halp "Summarize my recent shell activity and infer what I’ve been working on"
   ```

8) Environment grounding (OS, Python, Shell, CWD)
   
   ```bash
   halp "What OS, Python version, and shell am I using? Use the environment info provided"
   ```

9) Read a file and summarize (should propose a safe file read command)
   
   ```bash
   halp "Read the first 15 lines of README.md and summarize the project goals"
   ```

10) Git status summary (non-destructive)
    
    ```bash
    halp "Summarize the current Git status and list untracked files"
    ```

11) Processes by memory (auto-exec with yolo)
    
    ```bash
    halp "yolo list the top 5 processes by memory usage"
    ```

12) Check port usage (safe)
    
    ```bash
    halp "Check if port 8000 is listening and show matching processes"
    ```

13) Find Python files count under src/
    
    ```bash
    halp "Count how many Python files are under src/ and print the total"
    ```

14) List available models (API integration)
    
    ```bash
    halp -l
    ```

15) Interactive start + yolo directive
    
    ```bash
    halp
    # When prompted: yolo show the top 10 largest files under the repo
    # Confirmations should be skipped for this session.
    ```

Notes:
- If you want to avoid approving commands interactively in non-tty contexts, use `--unsafe_exec` or the `yolo` directive.
